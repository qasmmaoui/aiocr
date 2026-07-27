// L'écran-roi : chat streaming, chips sources, badges de version,
// boucle expert (صحيح/خطأ/أعترض) avec fiche d'اعتراض.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/api.dart';
import '../core/theme.dart';
import '../main.dart';
import '../shared/gazelle.dart';
import 'settings.dart';
import 'viewer.dart';

class Msg {
  final bool me;
  String text;
  List<Source> sources;
  bool streaming;
  bool error;
  String? feedbackGiven;
  Msg(this.me, this.text,
      {this.sources = const [], this.streaming = false, this.error = false});
}

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});
  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final msgs = <Msg>[];
  final inputC = TextEditingController();
  final scrollC = ScrollController();
  bool busy = false;

  Future<void> _ask(String q) async {
    if (q.trim().isEmpty || busy) return;
    final s = AppState.of(context).s;
    inputC.clear();
    final a = Msg(false, '', streaming: true);
    setState(() {
      msgs.add(Msg(true, q.trim()));
      msgs.add(a);
      busy = true;
    });
    _scroll();
    try {
      await for (final ev in Api.I.ask(q.trim())) {
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
      final p = await SharedPreferences.getInstance();
      final h = (jsonDecode(p.getString('history') ?? '[]') as List);
      h.insert(0, {
        'q': q,
        'law': a.sources.isNotEmpty ? a.sources.first.law : '',
        'n': a.sources.length,
        'ts': DateTime.now().toIso8601String(),
      });
      await p.setString('history', jsonEncode(h.take(100).toList()));
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
              onPressed: () => setState(() => msgs.clear()),
              icon: const Icon(Icons.add_comment_outlined)),
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
            child: Row(children: [
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
          child: Text(m.text,
              style: tt.bodyLarge!.copyWith(color: Colors.white, height: 1.7)),
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
        if (m.sources.isNotEmpty) ...[
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
        if (!m.streaming && !m.error && m.text.isNotEmpty) ...[
          const SizedBox(height: 10),
          Row(children: [
            _fbBtn(m, 'up', Icons.thumb_up_outlined, s.correct),
            const SizedBox(width: 6),
            _fbBtn(m, 'down', Icons.thumb_down_outlined, s.wrong),
            const SizedBox(width: 6),
            _fbBtn(m, 'contest', Icons.balance, s.contest,
                onTap: () => _contestSheet(m)),
          ]),
        ],
      ]),
    );
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
