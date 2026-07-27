// Réglages : compte, anneau d'usage, langue, thème, historique, déconnexion.
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/api.dart';
import '../core/theme.dart';
import '../main.dart';
import 'login.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});
  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  List<dynamic> history = [];

  @override
  void initState() {
    super.initState();
    Api.I.me().then((_) => mounted ? setState(() {}) : null);
    SharedPreferences.getInstance().then((p) {
      if (mounted) {
        setState(
            () => history = jsonDecode(p.getString('history') ?? '[]') as List);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final app = AppState.of(context);
    final s = app.s;
    final rl = context.rl;
    final tt = Theme.of(context).textTheme;
    final u = Api.I.usage;
    return Scaffold(
      appBar: AppBar(title: Text(s.settings)),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        // ── compte + usage ────────────────────────────────────────────
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
              color: rl.surface, border: Border.all(color: rl.hairline)),
          child: Row(children: [
            CircleAvatar(
                radius: 24,
                backgroundColor: rl.primary,
                child: Text(
                    (Api.I.fullname.isNotEmpty
                            ? Api.I.fullname
                            : Api.I.username)
                        .characters
                        .take(2)
                        .toString(),
                    style: const TextStyle(color: Colors.white))),
            const SizedBox(width: 14),
            Expanded(
              child:
                  Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(
                    Api.I.fullname.isNotEmpty
                        ? Api.I.fullname
                        : Api.I.username,
                    style: tt.titleMedium),
                if (u != null)
                  Text(
                      u.limit == null
                          ? '${u.plan} · ${s.unlimited}'
                          : s.usageOf(u.used, u.limit!),
                      style: tt.bodySmall),
              ]),
            ),
            if (u != null && u.limit != null)
              _UsageRing(
                  used: u.used,
                  limit: u.limit!,
                  color: rl.primary,
                  track: rl.sunk),
          ]),
        ),
        const SizedBox(height: 20),
        // ── préférences ───────────────────────────────────────────────
        Text(s.language, style: tt.bodySmall),
        const SizedBox(height: 6),
        SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'ar', label: Text('العربية')),
              ButtonSegment(value: 'fr', label: Text('Français')),
            ],
            selected: {app.locale},
            onSelectionChanged: (v) => app.setLocale(v.first)),
        const SizedBox(height: 16),
        Text(s.theme, style: tt.bodySmall),
        const SizedBox(height: 6),
        SegmentedButton<ThemeMode>(
            segments: [
              ButtonSegment(
                  value: ThemeMode.light, label: Text(s.themeLight)),
              ButtonSegment(value: ThemeMode.dark, label: Text(s.themeDark)),
              ButtonSegment(
                  value: ThemeMode.system, label: Text(s.themeSystem)),
            ],
            selected: {app.mode},
            onSelectionChanged: (v) => app.setMode(v.first)),
        const SizedBox(height: 24),
        // ── historique ────────────────────────────────────────────────
        Text(s.history, style: tt.titleMedium),
        const SizedBox(height: 8),
        if (history.isEmpty)
          Text('—', style: tt.bodySmall)
        else
          for (final h in history.take(20))
            Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                  color: rl.surface, border: Border.all(color: rl.hairline)),
              child:
                  Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(h['q'] as String? ?? '',
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: tt.bodyMedium),
                const SizedBox(height: 3),
                Text(
                    '${h['law'] ?? ''}${(h['n'] ?? 0) > 0 ? ' · ${h['n']} ${s.sources}' : ''}',
                    style: tt.bodySmall),
              ]),
            ),
        const SizedBox(height: 20),
        OutlinedButton.icon(
            onPressed: () async {
              await Api.I.logout();
              if (context.mounted) {
                Navigator.of(context).pushAndRemoveUntil(
                    MaterialPageRoute(builder: (_) => const LoginScreen()),
                    (_) => false);
              }
            },
            icon: Icon(Icons.logout, size: 18, color: rl.danger),
            label: Text(s.logout, style: TextStyle(color: rl.danger))),
        const SizedBox(height: 16),
        Center(
            child: Text(s.disclaimer,
                textAlign: TextAlign.center, style: tt.bodySmall)),
        const SizedBox(height: 8),
        Center(child: Text('RimLex v1.0', style: tt.labelSmall)),
      ]),
    );
  }
}

class _UsageRing extends StatelessWidget {
  final int used, limit;
  final Color color, track;
  const _UsageRing(
      {required this.used,
      required this.limit,
      required this.color,
      required this.track});

  @override
  Widget build(BuildContext context) => SizedBox(
        width: 46,
        height: 46,
        child: CustomPaint(
          painter: _RingPainter(
              frac: (used / math.max(1, limit)).clamp(0.0, 1.0),
              color: color,
              track: track),
          child: Center(
              child: Text('$used',
                  style: TextStyle(
                      fontFamily: kMono, fontSize: 13, color: color))),
        ),
      );
}

class _RingPainter extends CustomPainter {
  final double frac;
  final Color color, track;
  _RingPainter({required this.frac, required this.color, required this.track});

  @override
  void paint(Canvas canvas, Size s) {
    final c = Offset(s.width / 2, s.height / 2);
    final r = s.width / 2 - 3;
    canvas.drawCircle(
        c,
        r,
        Paint()
          ..color = track
          ..style = PaintingStyle.stroke
          ..strokeWidth = 4);
    canvas.drawArc(
        Rect.fromCircle(center: c, radius: r),
        -math.pi / 2,
        2 * math.pi * frac,
        false,
        Paint()
          ..color = color
          ..style = PaintingStyle.stroke
          ..strokeCap = StrokeCap.round
          ..strokeWidth = 4);
  }

  @override
  bool shouldRepaint(_RingPainter o) => o.frac != frac;
}
