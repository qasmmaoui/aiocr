# -*- coding: utf-8 -*-
"""Épreuves du stockage des pièces jointes.

On vérifie surtout ce qui ne pardonne pas : qu'une pièce d'une conversation
reste invisible depuis une autre, et que la purge efface le fichier sans
emporter le texte dont dépendent les questions de suivi.
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMP = tempfile.mkdtemp()
os.environ["CHAT_DB"] = os.path.join(_TMP, "chat.db")

from rag import memory                                   # noqa: E402
from services import attachments as att                  # noqa: E402


def _piece(sid, nom="convocation.pdf", texte="استدعاء للحضور أمام المحكمة"):
    pages = [{"num": 1, "type": "native", "text": texte,
              "preview": b"IMAGE-DE-LA-PAGE"}]
    return att.enregistrer(sid, nom, "application/pdf", b"%PDF-faux", pages,
                           "native")


def test_enregistre_et_relit():
    memory.init()
    sid = memory.create_session("essai")
    r = _piece(sid)
    assert r["nb_pages"] == 1 and r["etat"] == "pret"
    ctx = att.pour_contexte(sid, [r["id"]])
    assert len(ctx) == 1 and "استدعاء" in ctx[0]["texte"]


def test_apercus_non_conserves():
    """L'image de la page ne doit jamais entrer en base."""
    memory.init()
    sid = memory.create_session("apercu")
    r = _piece(sid)
    ctx = att.pour_contexte(sid, [r["id"]])
    assert "IMAGE-DE-LA-PAGE" not in ctx[0]["texte"]
    with att._cx() as cx:
        brut = cx.execute("SELECT pages FROM attachments WHERE id = ?",
                          (r["id"],)).fetchone()[0]
    assert "IMAGE" not in brut and "preview" not in brut


def test_cloisonnement_entre_conversations():
    """Un identifiant deviné ne doit pas ouvrir la pièce d'un autre dossier."""
    memory.init()
    a, b = memory.create_session("A"), memory.create_session("B")
    r = _piece(a, "dossier-client-A.pdf")
    assert att.pour_contexte(a, [r["id"]])          # son propriétaire la voit
    assert att.pour_contexte(b, [r["id"]]) == []    # l'autre, jamais


def test_nom_dorigine_jamais_sur_le_disque():
    """Deux « convocation.pdf » ne doivent pas s'écraser."""
    memory.init()
    sid = memory.create_session("noms")
    r1, r2 = _piece(sid), _piece(sid)
    with att._cx() as cx:
        c1 = cx.execute("SELECT chemin FROM attachments WHERE id=?", (r1["id"],)).fetchone()[0]
        c2 = cx.execute("SELECT chemin FROM attachments WHERE id=?", (r2["id"],)).fetchone()[0]
    assert c1 != c2
    assert "convocation" not in os.path.basename(c1)
    assert os.path.exists(c1) and os.path.exists(c2)


def test_purge_efface_le_fichier_et_garde_le_texte():
    memory.init()
    sid = memory.create_session("purge")
    r = _piece(sid)
    with att._cx() as cx:
        chemin = cx.execute("SELECT chemin FROM attachments WHERE id=?",
                            (r["id"],)).fetchone()[0]
    assert os.path.exists(chemin)

    # conversation encore active : on ne touche à rien
    att.purger()
    assert os.path.exists(chemin)

    # six minutes plus tard, le fichier s'en va. On compte le fichier visé et
    # non le retour de purger() : le balayeur traite toutes les conversations
    # expirées, y compris celles laissées par les autres épreuves.
    assert att.purger(time.time() + 6 * 60) >= 1
    assert not os.path.exists(chemin)

    # mais la question de suivi reste possible
    ctx = att.pour_contexte(sid, [r["id"]])
    assert ctx and "استدعاء" in ctx[0]["texte"]
    assert att.lister(sid)[0]["fichier_disponible"] is False


def test_purge_idempotente():
    memory.init()
    sid = memory.create_session("idem")
    _piece(sid)
    t = time.time() + 6 * 60
    assert att.purger(t) >= 1
    assert att.purger(t) == 0          # rien à refaire au second passage


def test_retrait_explicite():
    memory.init()
    sid = memory.create_session("retrait")
    r = _piece(sid)
    autre = memory.create_session("autre")
    assert att.supprimer(r["id"], autre) is False      # pas depuis ailleurs
    assert att.supprimer(r["id"], sid) is True
    assert att.pour_contexte(sid, [r["id"]]) == []


def test_oubli_de_session():
    memory.init()
    sid = memory.create_session("oubli")
    r = _piece(sid)
    att.oublier_session(sid)
    assert att.lister(sid) == []
    assert att.pour_contexte(sid, [r["id"]]) == []


def test_bornes_taille_et_nombre():
    memory.init()
    sid = memory.create_session("bornes")
    long_texte = "مادة " * 20_000
    r = _piece(sid, "gros.pdf", long_texte)
    ctx = att.pour_contexte(sid, [r["id"]])
    assert len(ctx[0]["texte"]) <= att.MAX_CAR_PIECE + 200
    assert "غير معروضة" in ctx[0]["texte"]

    ids = [_piece(sid, f"p{i}.pdf")["id"] for i in range(12)]
    assert len(att.pour_contexte(sid, ids)) <= att.MAX_PIECES


def test_bloc_pieces_annonce_des_faits_pas_du_droit():
    memory.init()
    sid = memory.create_session("bloc")
    r = _piece(sid)
    bloc = att.bloc_pieces(att.pour_contexte(sid, [r["id"]]))
    assert "وقائع الملف" in bloc and "وليست مصدرا للقانون" in bloc
    assert att.bloc_pieces([]) == ""


if __name__ == "__main__":
    fails = 0
    for nom, fn in sorted(globals().items()):
        if not nom.startswith("test_"):
            continue
        try:
            fn()
            print(f"  ok    {nom}")
        except AssertionError as e:
            fails += 1
            print(f"  ÉCHEC {nom}  {e}")
        except Exception as e:                       # noqa: BLE001
            fails += 1
            print(f"  ERREUR {nom}  {type(e).__name__}: {e}")
    print(("tout passe" if not fails else f"{fails} échec(s)"))
    sys.exit(1 if fails else 0)
