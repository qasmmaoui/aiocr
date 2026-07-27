// Thème RimLex — tokens exacts du handoff «RimLex Mobile App» (v1.0).
import 'package:flutter/material.dart';

abstract class RLColors {
  static const ink = Color(0xFF1C2B3A);
  static const inkDeep = Color(0xFF101A24);
  static const surfaceDark = Color(0xFF16232F);
  static const paper = Color(0xFFF7F6F2);
  static const paperSunk = Color(0xFFEDEAE1);
  static const hairline = Color(0xFFE4E1D8);
  static const hairlineDark = Color(0xFF22323F);
  static const green = Color(0xFF175A47);
  static const greenDark = Color(0xFF3E9C7E);
  static const gold = Color(0xFFA98A44);
  static const goldDark = Color(0xFFD9BC77);
  static const slate = Color(0xFF6B7A88);
  static const slateDark = Color(0xFF8A99A6);
  static const danger = Color(0xFFC0554A);
}

/// Extension de thème : couleurs sémantiques RimLex accessibles partout.
class RLTheme extends ThemeExtension<RLTheme> {
  final Color surface, sunk, hairline, text, meta, primary, gold, danger;
  const RLTheme(
      {required this.surface,
      required this.sunk,
      required this.hairline,
      required this.text,
      required this.meta,
      required this.primary,
      required this.gold,
      required this.danger});

  static const light = RLTheme(
      surface: Colors.white,
      sunk: RLColors.paperSunk,
      hairline: RLColors.hairline,
      text: RLColors.ink,
      meta: RLColors.slate,
      primary: RLColors.green,
      gold: RLColors.gold,
      danger: RLColors.danger);

  static const dark = RLTheme(
      surface: RLColors.surfaceDark,
      sunk: RLColors.inkDeep,
      hairline: RLColors.hairlineDark,
      text: RLColors.paper,
      meta: RLColors.slateDark,
      primary: RLColors.greenDark,
      gold: RLColors.goldDark,
      danger: RLColors.danger);

  @override
  RLTheme copyWith({Color? surface}) => this;
  @override
  RLTheme lerp(RLTheme? other, double t) => t < .5 ? this : (other ?? this);
}

const kSans = 'PlexArabic';
const kSerif = 'PlexSerif';
const kMono = 'PlexMono';
const kDisplay = 'Mansour'; // خط المغربي — titres & moments de marque

TextTheme _text(Color body, Color meta) => TextTheme(
      headlineMedium: TextStyle(
          fontFamily: kDisplay, fontSize: 26, height: 1.4, color: body),
      titleLarge: TextStyle(
          fontFamily: kSans,
          fontSize: 24,
          fontWeight: FontWeight.w600,
          height: 1.4,
          color: body),
      titleMedium: TextStyle(
          fontFamily: kSans,
          fontSize: 17,
          fontWeight: FontWeight.w600,
          height: 1.5,
          color: body),
      bodyLarge: TextStyle(
          fontFamily: kSans, fontSize: 16, height: 1.85, color: body),
      bodyMedium: TextStyle(
          fontFamily: kSans, fontSize: 14.5, height: 1.7, color: body),
      bodySmall: TextStyle(
          fontFamily: kSans, fontSize: 13.5, height: 1.7, color: meta),
      labelSmall: TextStyle(fontFamily: kMono, fontSize: 12, color: meta),
    );

ThemeData rlTheme(Brightness b) {
  final dark = b == Brightness.dark;
  final rl = dark ? RLTheme.dark : RLTheme.light;
  final scaffold = dark ? RLColors.inkDeep : RLColors.paper;
  return ThemeData(
    useMaterial3: true,
    brightness: b,
    scaffoldBackgroundColor: scaffold,
    fontFamily: kSans,
    colorScheme: ColorScheme.fromSeed(
        seedColor: rl.primary,
        brightness: b,
        primary: rl.primary,
        surface: rl.surface,
        error: rl.danger),
    textTheme: _text(rl.text, rl.meta),
    appBarTheme: AppBarTheme(
        backgroundColor: scaffold,
        foregroundColor: rl.text,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
            fontFamily: kSans,
            fontSize: 17,
            fontWeight: FontWeight.w600,
            color: rl.text)),
    filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
            backgroundColor: rl.primary,
            foregroundColor: Colors.white,
            minimumSize: const Size(48, 48),
            shape: const RoundedRectangleBorder(),
            textStyle: const TextStyle(
                fontFamily: kSans, fontSize: 16, fontWeight: FontWeight.w600))),
    outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
            foregroundColor: rl.text,
            minimumSize: const Size(48, 48),
            side: BorderSide(color: rl.hairline),
            shape: const RoundedRectangleBorder())),
    inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: rl.surface,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        border: OutlineInputBorder(
            borderRadius: BorderRadius.zero,
            borderSide: BorderSide(color: rl.hairline)),
        enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.zero,
            borderSide: BorderSide(color: rl.hairline)),
        focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.zero,
            borderSide: BorderSide(color: rl.primary, width: 1.4))),
    dividerTheme: DividerThemeData(color: rl.hairline, thickness: 1),
    extensions: [rl],
  );
}

extension RLThemeX on BuildContext {
  RLTheme get rl => Theme.of(this).extension<RLTheme>()!;
}
