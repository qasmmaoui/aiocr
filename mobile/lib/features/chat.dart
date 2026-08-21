// L'écran-roi : chat streaming, chips sources, badges de version,
// boucle expert (صحيح/خطأ/أعترض) avec fiche d'اعتراض.
import 'package:file_picker/file_picker.dart';
import 'package:flutter/services.dart';

import 'package:flutter/material.dart';

import '../core/api.dart';
import '../core/history.dart';
import '../core/theme.dart';
import '../main.dart';
import '../shared/gazelle.dart';
import 'history.dart';
import 'settings.dart';
import 'viewer.dart';

class Msg {
  final bool me;
  String text;
  String? question;          // question ayant produit cette réponse
  // Libellés des pièces envoyées avec ce message. On ne garde que le nom et
  // le nombre de pages : le fichier, lui, ne survit pas à la conversation.
  List<String> pieces = const [];
  List<Source> sources;
  bool streaming;
  bool error;
  String? feedbackGiven;
  Msg(this.me, this.text,
      {this.sources = const [], this.streaming = false, this.error = false});
}

class ChatScreen extends StatefulWidget {
  final Conversation? conversation;   // reprise d'une discussion existante
  const ChatScreen({super.key, this.conversation});
  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final msgs = <Msg>[];
  final inputC = TextEditingController();
  final scrollC = ScrollController();
  bool busy = false;
  late Conversation convo;
  String matiere = 'all';                 // matière priorisée
  List<Map<String, dynamic>> matieres = [];
  // Pièces déjà lues par le serveur et prêtes à accompagner la question.
  final pieces = <Piece>[];
  // Envois en cours : le nom s'affiche avant même que le serveur ait répondu,
  // sinon l'utilisateur croit que son clic n'a rien fait.
  final enCours = <String>[];
  // Question saisie pendant une transcription : elle part d'elle-même
  // dès que toutes les pièces sont lues.
  String? enAttente;

  @override
  void initState() {
    super.initState();
    convo = widget.conversation ??
        Conversation(
            id: History.newId(), title: '', updated: DateTime.now(),
            messages: []);
    for (final m in convo.messages) {
      msgs.add(Msg(m.me, m.text,
          sources: m.sources.map(Source.fromJson).toList()));
    }
    Api.I.matieres().then((l) {
      if (mounted) setState(() => matieres = l.where((m) => m['disponible'] == true).toList());
    });
  }

  /// Choisit des documents et les envoie un par un.
  ///
  /// Un par un, et non en bloc : l'utilisateur voit chaque pièce arriver, un
  /// échec ne concerne que le fichier fautif, et la lecture par le serveur se
  /// fait pendant qu'il continue de taper sa question.
  Future<void> _joindre() async {
    const acceptes = ['pdf', 'jpg', 'jpeg', 'png', 'webp', 'tif', 'tiff', 'bmp'];
    final s = AppState.of(context).s;
    FilePickerResult? choix;
    try {
      // `FileType.any` plutôt qu'un filtrage par extension : sur le web, le
      // filtre natif du sélecteur se comporte mal selon le navigateur. On
      // filtre nous-mêmes juste après, ce qui donne en prime un message clair
      // quand l'utilisateur choisit un format que le serveur refuserait.
      choix = await FilePicker.platform
          .pickFiles(allowMultiple: true, withData: true, type: FileType.any);
    } catch (e) {
      if (mounted) _prevenir('$e');
      return;
    }
    if (choix == null) return;
    for (final f in choix.files) {
      final ext = f.name.contains('.')
          ? f.name.split('.').last.toLowerCase()
          : '';
      if (!acceptes.contains(ext)) {
        _prevenir(s.ar
            ? 'صيغة غير مقبولة: ${f.name}'
            : 'Format non accepté : ${f.name}');
        continue;
      }
      final octets = f.bytes;
      if (octets == null) continue;
      if (pieces.length + enCours.length >= 10) {
        _prevenir(s.ar ? 'الحد الأقصى عشر وثائق.' : 'Dix documents au maximum.');
        break;
      }
      final cle = '${f.name}#${DateTime.now().microsecondsSinceEpoch}';
      setState(() => enCours.add(cle));
      try {
        final p = await Api.I.joindre(convo.id, f.name, octets, cle: cle);
        if (!mounted) return;
        // Envoi annulé pendant le transfert : la pièce est déjà chez le
        // serveur, on la retire pour ne pas la laisser traîner.
        if (!enCours.contains(cle)) {
          Api.I.retirerPiece(convo.id, p.id);
          continue;
        }
        setState(() => pieces.add(p));
        if (p.etat == 'lecture') _suivreLecture(p);
      } on PieceError catch (e) {
        if (mounted) _prevenir(e.message);
      } catch (_) {
        // Une annulation ferme le client, ce qui lève ici : rien à signaler.
        if (mounted && enCours.contains(cle)) {
          _prevenir(s.ar ? 'تعذر إرسال ${f.name}' : 'Échec de l\'envoi de ${f.name}');
        }
      } finally {
        if (mounted) setState(() => enCours.remove(cle));
      }
    }
  }

  /// Abandonne tout : transferts, transcriptions et question en attente.
  void _toutArreter() {
    for (final cle in List<String>.from(enCours)) {
      Api.I.annulerEnvoi(cle);
    }
    final aRetirer =
        pieces.where((p) => p.etat == 'lecture').toList(growable: false);
    setState(() {
      enCours.clear();
      enAttente = null;
      pieces.removeWhere((p) => p.etat == 'lecture');
    });
    // Retirer la pièce côté serveur interrompt sa transcription : le rapport
    // d'avancement ne trouve plus la ligne et lève.
    for (final p in aRetirer) {
      Api.I.retirerPiece(convo.id, p.id);
    }
  }

  /// Interrompt un envoi en cours de transfert.
  void _annulerEnvoi(String cle) {
    setState(() => enCours.remove(cle));
    Api.I.annulerEnvoi(cle);
  }

  /// Un scan se transcrit en arrière-plan — de trente à quatre-vingt-dix
  /// secondes par page. On interroge le serveur jusqu'à ce qu'il ait fini,
  /// plutôt que de tenir une requête ouverte que le proxy couperait.
  Future<void> _suivreLecture(Piece p) async {
    for (var i = 0; i < 200 && mounted; i++) {
      await Future<void>.delayed(const Duration(seconds: 3));
      if (!mounted || !pieces.contains(p)) return;   // retirée entre-temps
      final etats = await Api.I.etatPieces(convo.id);
      final maj = etats.where((e) => e.id == p.id);
      if (maj.isEmpty) return;
      if (mounted) setState(() => p.progres = maj.first.progres);
      if (maj.first.etat != 'lecture') {
        if (mounted) setState(() => p.etat = maj.first.etat);
        // Une question mise en attente part dès que tout est lu.
        if (enAttente != null && !pieces.any((x) => x.etat == 'lecture')) {
          final q = enAttente!;
          enAttente = null;
          _ask(q);
        }
        return;
      }
    }
  }

  void _prevenir(String texte) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(texte)));
  }

  Future<void> _retirer(Piece p) async {
    setState(() => pieces.remove(p));
    try {
      await Api.I.retirerPiece(convo.id, p.id);
    } catch (_) {
      // le retrait local suffit : le balayeur du serveur fera le reste
    }
  }

  Future<void> _ask(String q) async {
    if (q.trim().isEmpty || busy) return;
    final s = AppState.of(context).s;
    // Partir avant la fin de la transcription reviendrait à interroger un
    // document vide — et la génération se disputerait le GPU avec la lecture,
    // ralentissant les deux.
    if (pieces.any((p) => p.etat == 'lecture') || enCours.isNotEmpty) {
      // La question n'est pas refusée : elle attend la fin de la lecture et
      // part toute seule. Interroger un document à moitié transcrit donnerait
      // une réponse fondée sur du vide.
      setState(() => enAttente = q.trim());
      inputC.clear();
      _prevenir(s.ar
          ? 'سيُرسل سؤالك بعد انتهاء قراءة الوثائق.'
          : 'Votre question partira dès la fin de la lecture.');
      return;
    }
    inputC.clear();
    final jointes = List<Piece>.from(pieces);
    final a = Msg(false, '', streaming: true)..question = q.trim();
    setState(() {
      msgs.add(Msg(true, q.trim())
        ..pieces = jointes.map((p) => '${p.filename} · ${p.nbPages}p').toList());
      msgs.add(a);
      busy = true;
      // Les pièces restent connues du serveur pour les questions de suivi ;
      // on vide seulement la zone de saisie.
      pieces.clear();
    });
    _scroll();
    try {
      await for (final ev in Api.I.ask(q.trim(),
          matiere: matiere, sessionId: convo.id,
          attachmentIds: jointes.map((p) => p.id).toList())) {
        if (ev.sources != null) a.sources = ev.sources!;
        if (ev.delta != null) a.text += ev.delta!;
        if (mounted) setState(() {});
        _scroll();
      }
    } on QuotaError {
      a.text = s.quotaReached;
      a.error = true;
    } catch (_) {
      if (a.text.isEmpty) {
        a.text = s.genFailed;
        a.error = true;
      }
    } finally {
      a.streaming = false;
      busy = false;
      if (mounted) setState(() {});
      _saveHistory(q.trim(), a);
      Api.I.me().then((_) => mounted ? setState(() {}) : null);
    }
  }

  Future<void> _saveHistory(String q, Msg a) async {
    try {
      if (convo.title.isEmpty) convo.title = History.titleFrom(q);
      convo.messages = [
        for (final m in msgs)
          StoredMessage(m.me, m.text, [
            for (final s in m.sources)
              {'law': s.law, 'file': s.file, 'article': s.article,
               'chunk': s.chunk}
          ])
      ];
      await History.save(convo);
    } catch (_) {}
  }

  void _scroll() => WidgetsBinding.instance.addPostFrameCallback((_) {
        if (scrollC.hasClients) {
          scrollC.animateTo(scrollC.position.maxScrollExtent + 120,
              duration: const Duration(milliseconds: 200),
              curve: Curves.easeOut);
        }
      });

  Future<void> _feedback(Msg a, String type, [String comment = '']) async {
    final s = AppState.of(context).s;
    final q = msgs.lastWhere((m) => m.me, orElse: () => Msg(true, '')).text;
    await Api.I.feedback(type, q, a.text, a.sources, comment);
    setState(() => a.feedbackGiven = type);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(type == 'contest' ? s.contestDone : s.feedbackDone)));
    }
  }

  void _contestSheet(Msg a) {
    final s = AppState.of(context).s;
    final rl = context.rl;
    final c = TextEditingController();
    showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        backgroundColor: rl.surface,
        shape: const RoundedRectangleBorder(),
        builder: (ctx) => Padding(
              padding: EdgeInsets.only(
                  left: 20,
                  right: 20,
                  top: 20,
                  bottom: MediaQuery.of(ctx).viewInsets.bottom + 20),
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Row(children: [
                  Icon(Icons.balance, color: rl.gold, size: 20),
                  const SizedBox(width: 8),
                  Text(s.contest,
                      style: Theme.of(ctx).textTheme.titleMedium),
                ]),
                const SizedBox(height: 12),
                TextField(
                    controller: c,
                    maxLines: 4,
                    autofocus: true,
                    decoration: InputDecoration(hintText: s.contestHint)),
                const SizedBox(height: 14),
                Row(children: [
                  Expanded(
                      child: FilledButton(
                          onPressed: () {
                            Navigator.pop(ctx);
                            _feedback(a, 'contest', c.text.trim());
                          },
                          child: Text(s.contestSend))),
                ]),
              ]),
            ));
  }

  @override
  Widget build(BuildContext context) {
    final app = AppState.of(context);
    final s = app.s;
    final rl = context.rl;
    return Scaffold(
      appBar: AppBar(
        title: Row(children: [
          Gazelle(size: 30, ink: rl.text, gold: rl.gold, gaze: false),
          const SizedBox(width: 10),
          Text(s.appName),
        ]),
        actions: [
          IconButton(
              tooltip: s.newChat,
              onPressed: () => setState(() {
                    msgs.clear();
                    convo = Conversation(
                        id: History.newId(), title: '',
                        updated: DateTime.now(), messages: []);
                  }),
              icon: const Icon(Icons.add_comment_outlined)),
          IconButton(
              tooltip: s.history,
              onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const HistoryScreen())),
              icon: const Icon(Icons.history)),
          IconButton(
              tooltip: s.settings,
              onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const SettingsScreen())),
              icon: const Icon(Icons.settings_outlined)),
        ],
      ),
      body: Column(children: [
        Expanded(
          child: msgs.isEmpty
              ? _Empty(onTap: _ask)
              : ListView.builder(
                  controller: scrollC,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  itemCount: msgs.length,
                  itemBuilder: (_, i) => _bubble(msgs[i])),
        ),
        SafeArea(
          top: false,
          child: Container(
            decoration: BoxDecoration(
                color: rl.surface,
                border: Border(top: BorderSide(color: rl.hairline))),
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              if (matieres.isNotEmpty)
                SizedBox(
                  height: 34,
                  child: ListView(
                    scrollDirection: Axis.horizontal,
                    children: [
                      _matChip('all', s.ar ? 'كل المواد' : 'Toutes'),
                      for (final m in matieres)
                        _matChip(m['key'] as String,
                            (s.ar ? m['ar'] : m['fr']) as String),
                    ],
                  ),
                ),
              // Lecture en cours : on dit ce qui se passe et on offre la
              // sortie. Sans ce bouton, l'utilisateur qui renonce laisse le
              // modèle de vision travailler — et facturer — dans le vide.
              if (pieces.any((p) => p.etat == 'lecture') || enCours.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Row(children: [
                    Expanded(
                      child: Text(
                          enAttente != null
                              ? (s.ar
                                  ? 'سيُرسل سؤالك بعد انتهاء القراءة…'
                                  : 'Question en attente de la lecture…')
                              : (s.ar ? 'قراءة الوثائق…' : 'Lecture des documents…'),
                          style: TextStyle(fontSize: 12, color: rl.meta)),
                    ),
                    TextButton(
                      onPressed: _toutArreter,
                      child: Text(s.ar ? 'إيقاف' : 'Tout arrêter',
                          style: TextStyle(fontSize: 12.5, color: rl.danger)),
                    ),
                  ]),
                ),
              // Vignettes des pièces : visibles avant l'envoi, retirables une
              // à une. Une carte — nom et nombre de pages — jamais l'image de
              // la page, qui ne survit pas à la conversation.
              if (pieces.isNotEmpty || enCours.isNotEmpty)
                Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Wrap(spacing: 6, runSpacing: 6, children: [
                      for (final p in pieces)
                        _vignette(
                            p.etat == 'lecture'
                                ? '${p.filename}  ·  ${p.progres}%'
                                : p.etat == 'echec'
                                    ? '${p.filename}  ·  ${s.ar ? "تعذرت القراءة" : "illisible"}'
                                    : '${p.filename}  ·  ${p.nbPages}p',
                            onRetirer: () => _retirer(p),
                            enCours: p.etat == 'lecture'),
                      for (final cle in enCours)
                        _vignette(cle.split('#').first,
                            onRetirer: () => _annulerEnvoi(cle),
                            enCours: true),
                    ]),
                  ),
                ),
              Row(children: [
              IconButton(
                onPressed: busy ? null : _joindre,
                tooltip: s.ar ? 'إرفاق وثيقة' : 'Joindre un document',
                icon: Icon(Icons.attach_file, size: 22, color: rl.meta),
              ),
              Expanded(
                child: TextField(
                    controller: inputC,
                    minLines: 1,
                    maxLines: 4,
                    textInputAction: TextInputAction.send,
                    onSubmitted: _ask,
                    decoration: InputDecoration(
                        hintText: s.askHint,
                        border: InputBorder.none,
                        enabledBorder: InputBorder.none,
                        focusedBorder: InputBorder.none,
                        filled: false)),
              ),
              const SizedBox(width: 6),
              SizedBox(
                width: 48,
                height: 48,
                child: FilledButton(
                    onPressed: busy ? null : () => _ask(inputC.text),
                    style: FilledButton.styleFrom(
                        padding: EdgeInsets.zero,
                        backgroundColor: rl.primary),
                    child: Icon(
                        s.ar ? Icons.arrow_back : Icons.arrow_forward,
                        size: 22)),
              ),
            ]),
            ]),
          ),
        ),
      ]),
    );
  }

  Widget _bubble(Msg m) {
    final s = AppState.of(context).s;
    final rl = context.rl;
    final tt = Theme.of(context).textTheme;
    if (m.me) {
      return Align(
        alignment: AlignmentDirectional.centerStart,
        child: GestureDetector(
          onLongPress: () => _copy(m.text, s.copied),
          child: Container(
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
          constraints: BoxConstraints(
              maxWidth: MediaQuery.of(context).size.width * .82),
          decoration: BoxDecoration(
              color: rl.primary,
              borderRadius: const BorderRadiusDirectional.only(
                  topStart: Radius.circular(4),
                  topEnd: Radius.circular(16),
                  bottomStart: Radius.circular(16),
                  bottomEnd: Radius.circular(16))),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                // Les pièces restent visibles dans l'historique : le fichier a
                // pu être effacé, la trace de ce qui a été envoyé demeure.
                if (m.pieces.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Wrap(spacing: 6, runSpacing: 6, children: [
                      for (final p in m.pieces)
                        Row(mainAxisSize: MainAxisSize.min, children: [
                          const Icon(Icons.description_outlined,
                              size: 14, color: Colors.white70),
                          const SizedBox(width: 4),
                          ConstrainedBox(
                            constraints: const BoxConstraints(maxWidth: 200),
                            child: Text(p,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                    fontSize: 12, color: Colors.white70)),
                          ),
                        ]),
                    ]),
                  ),
                Text(m.text,
                    style: tt.bodyLarge!
                        .copyWith(color: Colors.white, height: 1.7)),
              ],
            ),
          ),
        ),
      );
    }
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
          color: rl.surface, border: Border.all(color: rl.hairline)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Gazelle(size: 20, ink: rl.gold, gold: rl.gold, gaze: false),
          const SizedBox(width: 6),
          Text('RIMLEX', style: tt.labelSmall),
        ]),
        const SizedBox(height: 8),
        if (m.streaming && m.text.isEmpty)
          Row(children: [
            GazelleThinking(size: 40, ink: rl.text, leap: rl.primary),
            const SizedBox(width: 10),
            Flexible(child: Text(s.thinking, style: tt.bodySmall)),
          ])
        else
          Text(m.text,
              style: m.error
                  ? tt.bodyMedium!.copyWith(color: rl.danger)
                  : tt.bodyLarge),
        // Les sources n'apparaissent qu'une fois la réponse écrite : afficher
        // des références avant de savoir ce qu'elles fondent induit en erreur.
        if (!m.streaming && m.sources.isNotEmpty) ...[
          const SizedBox(height: 10),
          Divider(height: 1, color: rl.hairline),
          const SizedBox(height: 8),
          Text(s.sources, style: tt.labelSmall),
          const SizedBox(height: 6),
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (var i = 0; i < m.sources.length; i++)
              _SourceChip(index: i + 1, source: m.sources[i]),
          ]),
        ],
        if (!m.streaming && m.text.isNotEmpty) ...[
          const SizedBox(height: 10),
          Wrap(spacing: 6, runSpacing: 6, children: [
            // en cas d'échec, seules les actions utiles restent : relancer,
            // copier — juger une réponse qui n'existe pas n'a pas de sens.
            if (!m.error) ...[
              _fbBtn(m, 'up', Icons.thumb_up_outlined, s.correct),
              _fbBtn(m, 'down', Icons.thumb_down_outlined, s.wrong),
              _fbBtn(m, 'contest', Icons.balance, s.contest,
                  onTap: () => _contestSheet(m)),
            ],
            if (m.question != null)
              _actBtn(Icons.refresh, s.resubmit, () => _ask(m.question!)),
            _actBtn(Icons.copy_outlined, s.copyAnswer,
                () => _copy(m.text, s.copied)),
          ]),
        ],
      ]),
    );
  }


  /// Carte d'une pièce jointe : nom, nombre de pages, et une croix pour la
  /// retirer. Pas d'aperçu de page — le fichier ne survit pas à la
  /// conversation, en montrer une reproduction serait contradictoire.
  Widget _vignette(String label, {VoidCallback? onRetirer, bool enCours = false}) {
    final rl = context.rl;
    return Container(
      padding: const EdgeInsetsDirectional.only(
          start: 10, end: 4, top: 6, bottom: 6),
      decoration: BoxDecoration(
          color: rl.sunk,
          border: Border.all(color: rl.hairline),
          borderRadius: BorderRadius.circular(8)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        if (enCours)
          SizedBox(
              width: 13,
              height: 13,
              child: CircularProgressIndicator(strokeWidth: 2, color: rl.meta))
        else
          Icon(Icons.description_outlined, size: 15, color: rl.meta),
        const SizedBox(width: 6),
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 190),
          child: Text(label,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 12.5, color: rl.text)),
        ),
        if (onRetirer != null)
          InkWell(
            onTap: onRetirer,
            child: Padding(
              padding: const EdgeInsets.all(4),
              child: Icon(Icons.close, size: 14, color: rl.meta),
            ),
          )
        else
          const SizedBox(width: 6),
      ]),
    );
  }

  Widget _matChip(String key, String label) {
    final rl = context.rl;
    final on = matiere == key;
    return Padding(
      padding: const EdgeInsetsDirectional.only(end: 6),
      child: InkWell(
        onTap: () => setState(() => matiere = key),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
              color: on ? rl.primary : Colors.transparent,
              border: Border.all(color: on ? rl.primary : rl.hairline),
              borderRadius: BorderRadius.circular(999)),
          child: Text(label,
              style: TextStyle(
                  fontSize: 12.5,
                  color: on ? Colors.white : rl.meta,
                  fontWeight: on ? FontWeight.w600 : FontWeight.w400)),
        ),
      ),
    );
  }

  Widget _actBtn(IconData ic, String label, VoidCallback onTap) {
    final rl = context.rl;
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
        decoration: BoxDecoration(
            border: Border.all(color: rl.hairline),
            borderRadius: BorderRadius.circular(999)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(ic, size: 15, color: rl.meta),
          const SizedBox(width: 5),
          Text(label, style: TextStyle(fontSize: 12.5, color: rl.meta)),
        ]),
      ),
    );
  }

  void _copy(String text, String done) {
    Clipboard.setData(ClipboardData(text: text));
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(done)));
  }

  Widget _fbBtn(Msg m, String type, IconData ic, String label,
      {VoidCallback? onTap}) {
    final rl = context.rl;
    final given = m.feedbackGiven == type;
    return InkWell(
      onTap: m.feedbackGiven != null
          ? null
          : (onTap ?? () => _feedback(m, type)),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
        decoration: BoxDecoration(
            color: given ? rl.sunk : Colors.transparent,
            border: Border.all(color: rl.hairline),
            borderRadius: BorderRadius.circular(999)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(ic, size: 15, color: given ? rl.primary : rl.meta),
          const SizedBox(width: 5),
          Text(label,
              style: TextStyle(
                  fontSize: 12.5, color: given ? rl.primary : rl.meta)),
          if (given) ...[
            const SizedBox(width: 3),
            Icon(Icons.check, size: 13, color: rl.primary),
          ],
        ]),
      ),
    );
  }
}

class _SourceChip extends StatelessWidget {
  final int index;
  final Source source;
  const _SourceChip({required this.index, required this.source});

  @override
  Widget build(BuildContext context) {
    final rl = context.rl;
    final label = source.article != null && source.article != 'None'
        ? '${source.law} · م.${source.article}'
        : source.law;
    return InkWell(
      onTap: () => Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => ViewerScreen(source: source))),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
            color: rl.sunk,
            border: Border.all(color: rl.hairline),
            borderRadius: BorderRadius.circular(999)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          CircleAvatar(
              radius: 9,
              backgroundColor: rl.primary,
              child: Text('$index',
                  style: const TextStyle(fontSize: 10, color: Colors.white))),
          const SizedBox(width: 6),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 180),
            child: Text(label,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 12.5, color: rl.text)),
          ),
          const SizedBox(width: 4),
          Icon(Icons.remove_red_eye_outlined, size: 13, color: rl.gold),
        ]),
      ),
    );
  }
}

class _Empty extends StatelessWidget {
  final void Function(String) onTap;
  const _Empty({required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppState.of(context).s;
    final rl = context.rl;
    final tt = Theme.of(context).textTheme;
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(28),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Column(children: [
            Gazelle(size: 110, ink: rl.text, gold: rl.gold),
            const SizedBox(height: 20),
            Text(s.emptyTitle,
                textAlign: TextAlign.center, style: tt.titleLarge),
            const SizedBox(height: 8),
            Text(s.emptyBody,
                textAlign: TextAlign.center, style: tt.bodySmall),
            const SizedBox(height: 24),
            for (var i = 0; i < s.starters.length; i++) ...[
              InkWell(
                onTap: () => onTap(s.starters[i]),
                child: Container(
                  width: double.infinity,
                  margin: const EdgeInsets.only(bottom: 10),
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                      color: rl.surface,
                      border: Border.all(color: rl.hairline)),
                  child: Row(children: [
                    Text('٠${i + 1}',
                        style:
                            TextStyle(fontFamily: kMono, color: rl.gold)),
                    const SizedBox(width: 12),
                    Expanded(
                        child: Text(s.starters[i], style: tt.bodyMedium)),
                  ]),
                ),
              ),
            ],
          ]),
        ),
      ),
    );
  }
}
