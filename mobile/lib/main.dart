// RimLex Mobile — point d'entrée : état global (langue, thème, session),
// splash avec la gazelle, routage login → chat.
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'core/api.dart';
import 'core/strings.dart';
import 'core/theme.dart';
import 'features/chat.dart';
import 'features/login.dart';
import 'shared/gazelle.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const RimLexApp());
}

class AppState extends InheritedWidget {
  final String locale;
  final ThemeMode mode;
  final void Function(String) setLocale;
  final void Function(ThemeMode) setMode;
  final VoidCallback onAuthChanged;
  const AppState(
      {super.key,
      required this.locale,
      required this.mode,
      required this.setLocale,
      required this.setMode,
      required this.onAuthChanged,
      required super.child});

  S get s => S(locale);
  static AppState of(BuildContext c) =>
      c.dependOnInheritedWidgetOfExactType<AppState>()!;
  @override
  bool updateShouldNotify(AppState old) =>
      old.locale != locale || old.mode != mode;
}

class RimLexApp extends StatefulWidget {
  const RimLexApp({super.key});
  @override
  State<RimLexApp> createState() => _RimLexAppState();
}

class _RimLexAppState extends State<RimLexApp> {
  String locale = 'ar';
  ThemeMode mode = ThemeMode.system;
  bool ready = false;

  @override
  void initState() {
    super.initState();
    _boot();
  }

  Future<void> _boot() async {
    final p = await SharedPreferences.getInstance();
    locale = p.getString('locale') ?? 'ar';
    final m = p.getString('mode') ?? 'system';
    mode = ThemeMode.values.firstWhere((v) => v.name == m,
        orElse: () => ThemeMode.system);
    await Api.I.init();
    // splash minimal 1.5 s — le temps du «regard» de la gazelle
    await Future.delayed(const Duration(milliseconds: 1500));
    if (mounted) setState(() => ready = true);
  }

  @override
  Widget build(BuildContext context) {
    final s = S(locale);
    return AppState(
      locale: locale,
      mode: mode,
      setLocale: (l) async {
        setState(() => locale = l);
        (await SharedPreferences.getInstance()).setString('locale', l);
      },
      setMode: (m) async {
        setState(() => mode = m);
        (await SharedPreferences.getInstance()).setString('mode', m.name);
      },
      onAuthChanged: () => setState(() {}),
      child: MaterialApp(
        title: 'RimLex',
        debugShowCheckedModeBanner: false,
        theme: rlTheme(Brightness.light),
        darkTheme: rlTheme(Brightness.dark),
        themeMode: mode,
        builder: (c, child) =>
            Directionality(textDirection: s.dir, child: child!),
        home: !ready
            ? const _Splash()
            : (Api.I.loggedIn ? const ChatScreen() : const LoginScreen()),
      ),
    );
  }
}

class _Splash extends StatelessWidget {
  const _Splash();
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: RLColors.paper,
      body: Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Gazelle(size: 140, ink: RLColors.ink, gold: RLColors.gold),
          const SizedBox(height: 24),
          Text('RimLex',
              style: TextStyle(
                  fontFamily: kDisplay,
                  fontSize: 34,
                  color: RLColors.ink,
                  height: 1.2)),
          const SizedBox(height: 4),
          const Text('ريم لكس · الإدارة بالحجة',
              style: TextStyle(
                  fontFamily: kSans, fontSize: 14, color: RLColors.slate)),
        ]),
      ),
    );
  }
}
