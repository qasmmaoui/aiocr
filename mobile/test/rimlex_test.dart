import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rimlex_mobile/core/strings.dart';
import 'package:rimlex_mobile/core/theme.dart';
import 'package:rimlex_mobile/features/login.dart';
import 'package:rimlex_mobile/main.dart';
import 'package:rimlex_mobile/shared/gazelle.dart';

Widget host(Widget child, {String locale = 'ar'}) => AppState(
      locale: locale,
      mode: ThemeMode.light,
      setLocale: (_) {},
      setMode: (_) {},
      onAuthChanged: () {},
      child: MaterialApp(
        theme: rlTheme(Brightness.light),
        home: Directionality(
            textDirection: S(locale).dir, child: child),
      ),
    );

void main() {
  group('Identité et thème', () {
    test('les tokens du handoff sont respectés', () {
      expect(RLColors.ink, const Color(0xFF1C2B3A));
      expect(RLColors.green, const Color(0xFF175A47));
      expect(RLColors.gold, const Color(0xFFA98A44));
      expect(RLColors.paper, const Color(0xFFF7F6F2));
    });

    test('le corps de texte respecte le minimum arabe (16sp, interligne 1.8+)',
        () {
      final t = rlTheme(Brightness.light).textTheme.bodyLarge!;
      expect(t.fontSize! >= 16, isTrue);
      expect(t.height! >= 1.8, isTrue);
    });

    test('les deux thèmes existent avec des fonds distincts', () {
      expect(rlTheme(Brightness.light).scaffoldBackgroundColor,
          isNot(rlTheme(Brightness.dark).scaffoldBackgroundColor));
    });
  });

  group('Localisation', () {
    test("l'arabe est RTL et le français LTR", () {
      expect(const S('ar').dir, TextDirection.rtl);
      expect(const S('fr').dir, TextDirection.ltr);
    });

    test('chaque libellé clé existe dans les deux langues', () {
      for (final s in [const S('ar'), const S('fr')]) {
        expect(s.login.isNotEmpty, isTrue);
        expect(s.contest.isNotEmpty, isTrue);
        expect(s.sources.isNotEmpty, isTrue);
        expect(s.disclaimer.isNotEmpty, isTrue);
        expect(s.starters.length, 3);
      }
    });

    test('le compteur d\'usage se formate dans les deux langues', () {
      expect(const S('ar').usageOf(12, 50).contains('12'), isTrue);
      expect(const S('fr').usageOf(12, 50).contains('50'), isTrue);
    });
  });

  group('Écran de connexion', () {
    testWidgets('affiche marque, champs et avertissement (AR)', (t) async {
      await t.pumpWidget(host(const LoginScreen()));
      await t.pump();
      expect(find.text('ريم لكس'), findsOneWidget);
      expect(find.text('الإدارة بالحجة'), findsOneWidget);
      expect(find.byType(TextField), findsNWidgets(2));
      expect(find.textContaining('النص الأصلي وحده هو الحجة'), findsOneWidget);
      expect(find.byType(Gazelle), findsOneWidget);
    });

    testWidgets('bascule en français en LTR', (t) async {
      await t.pumpWidget(host(const LoginScreen(), locale: 'fr'));
      await t.pump();
      expect(find.text('Se connecter'), findsOneWidget);
      expect(find.textContaining('seul le texte original'), findsOneWidget);
    });
  });

  group('Gazelle', () {
    testWidgets('emblème et boucle de réflexion se rendent', (t) async {
      await t.pumpWidget(host(const Column(children: [
        Gazelle(size: 80, ink: RLColors.ink, gold: RLColors.gold),
        GazelleThinking(size: 40, ink: RLColors.ink, leap: RLColors.green),
      ])));
      await t.pump(const Duration(milliseconds: 160));
      await t.pump(const Duration(milliseconds: 160));
      expect(find.byType(Gazelle), findsOneWidget);
      expect(find.byType(GazelleThinking), findsOneWidget);
    });
  });
}
