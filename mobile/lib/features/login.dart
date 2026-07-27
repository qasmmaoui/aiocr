// Écran de connexion — sobre, institutionnel.
import 'package:flutter/material.dart';

import '../core/api.dart';
import '../core/theme.dart';
import '../main.dart';
import '../shared/gazelle.dart';
import 'chat.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final userC = TextEditingController();
  final passC = TextEditingController();
  final serverC = TextEditingController();
  bool busy = false;
  String? error;
  bool showServer = false;

  @override
  void initState() {
    super.initState();
    serverC.text = Api.I.base;
  }

  Future<void> _go() async {
    final s = AppState.of(context).s;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      Api.I.base = serverC.text.trim();
      await Api.I.login(userC.text.trim(), passC.text);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const ChatScreen()));
    } catch (_) {
      setState(() => error = s.loginFailed);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = AppState.of(context);
    final s = app.s;
    final rl = context.rl;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child:
                  Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                const SizedBox(height: 12),
                Center(
                    child: Gazelle(
                        size: 96, ink: rl.text, gold: rl.gold)),
                const SizedBox(height: 16),
                Center(
                    child: Text(s.appName,
                        style: Theme.of(context).textTheme.headlineMedium)),
                Center(
                    child: Text(s.tagline,
                        style: Theme.of(context).textTheme.bodySmall)),
                const SizedBox(height: 32),
                TextField(
                    controller: userC,
                    autofillHints: const [AutofillHints.username],
                    decoration: InputDecoration(labelText: s.username)),
                const SizedBox(height: 12),
                TextField(
                    controller: passC,
                    obscureText: true,
                    autofillHints: const [AutofillHints.password],
                    onSubmitted: (_) => _go(),
                    decoration: InputDecoration(labelText: s.password)),
                if (error != null) ...[
                  const SizedBox(height: 10),
                  Text(error!,
                      style: TextStyle(color: rl.danger, fontSize: 13.5)),
                ],
                const SizedBox(height: 20),
                FilledButton(
                    onPressed: busy ? null : _go,
                    child: busy
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white))
                        : Text(s.login)),
                const SizedBox(height: 16),
                Center(
                  child: TextButton(
                      onPressed: () =>
                          setState(() => showServer = !showServer),
                      child: Text(s.serverUrl,
                          style: TextStyle(color: rl.meta, fontSize: 12.5))),
                ),
                if (showServer)
                  TextField(
                      controller: serverC,
                      textDirection: TextDirection.ltr,
                      style: const TextStyle(fontFamily: kMono, fontSize: 13),
                      decoration:
                          const InputDecoration(hintText: 'http://…:8000')),
                const SizedBox(height: 24),
                Center(
                    child: Text(s.disclaimer,
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.bodySmall)),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}
