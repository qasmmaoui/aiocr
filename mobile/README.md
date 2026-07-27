# RimLex Mobile (Flutter)

> Le chat RimLex dans la poche : poser une question juridique, lire une réponse
> ancrée, **ouvrir la page originale de la loi** (عين الريم), contester.
> Arabe RTL par défaut, français secondaire.

## Démarrer

```bash
flutter pub get
flutter run                      # appareil/émulateur
flutter run -d chrome            # web
```

L'adresse du backend est modifiable **depuis l'écran de connexion** («عنوان الخادم»).
Valeurs par défaut : `http://10.0.2.2:8000` (émulateur Android → hôte),
et en web, l'origine de la page (l'API sert l'app sur `/app`).

Surcharge à la compilation :

```bash
flutter run --dart-define=RIMLEX_API=https://rimlex.example.ma
```

## Builds

```bash
flutter test                                   # 10 tests (identité, l10n, écrans)
flutter analyze                                # doit être vide
flutter build web --release --base-href /app/  # servi par FastAPI sur /app
flutter build apk --release                    # build/app/outputs/flutter-apk/
```

Le build web est aussi une **PWA installable** (manifeste arabe, icônes gazelle) :
sur téléphone, «Ajouter à l'écran d'accueil» suffit — pas besoin de store pour
le pilote.

## Architecture

```
lib/
  core/    theme.dart     tokens exacts du handoff (couleurs, type, géométrie)
           strings.dart   i18n AR/FR + direction du texte
           api.dart       JWT (access + refresh rotatif), streaming NDJSON
  shared/  gazelle.dart   emblème + boucle «réflexion» 3 frames × 140 ms
  features/
           login.dart     connexion (+ réglage serveur)
           chat.dart      écran principal : streaming, chips sources, 👍/👎/أعترض
           viewer.dart    عين الريم — page originale zoomable, badge de version
           settings.dart  compte, anneau d'usage, langue, thème, historique
```

## Contrat API utilisé

| Endpoint | Usage |
|---|---|
| `POST /api/mobile/auth/login` | jetons + profil + quota |
| `POST /api/mobile/auth/refresh` | rotation (l'ancien refresh est révoqué) |
| `GET /api/mobile/me` | profil + usage du mois |
| `POST /api/chat/stream` | réponse en streaming NDJSON (Bearer → quota décompté) |
| `GET /api/viewer/chunk-info` | page du passage, nombre de pages, statut de version |
| `GET /api/viewer/page-image` | image de la page (surlignage or, `clean=1` sans filigrane) |
| `POST /api/feedback` | boucle expert : 👍 / 👎 / أعترض |

## Publication (à faire par le propriétaire du produit)

1. Compte Google Play (25 $ une fois) et/ou Apple Developer (99 $/an + macOS)
2. Signature : créer un keystore, renseigner `android/key.properties`
3. Politique de confidentialité + CGU en ligne (exigées par les deux stores)
4. `flutter build appbundle --release` → dépôt sur Play Console

Tant que ce n'est pas fait, distribuez l'**APK** (test interne) ou la **PWA**.
