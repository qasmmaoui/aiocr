// Écran Historique : liste des conversations, ouverture pour lecture ET
// poursuite, suppression. Groupé par jour.
import 'package:flutter/material.dart';

import '../core/history.dart';
import '../core/theme.dart';
import '../main.dart';
import 'chat.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});
  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  List<Conversation> items = [];
  bool loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final l = await History.all();
    if (mounted) {
      setState(() {
        items = l;
        loading = false;
      });
    }
  }

  String _dayLabel(DateTime d) {
    final s = AppState.of(context).s;
    final now = DateTime.now();
    final day = DateTime(d.year, d.month, d.day);
    final today = DateTime(now.year, now.month, now.day);
    final diff = today.difference(day).inDays;
    if (diff == 0) return s.today;
    if (diff == 1) return s.yesterday;
    return '${d.day}/${d.month}/${d.year}';
  }

  @override
  Widget build(BuildContext context) {
    final s = AppState.of(context).s;
    final rl = context.rl;
    final tt = Theme.of(context).textTheme;

    Widget body;
    if (loading) {
      body = const Center(child: CircularProgressIndicator());
    } else if (items.isEmpty) {
      body = Center(child: Text(s.noHistory, style: tt.bodySmall));
    } else {
      String? lastDay;
      final children = <Widget>[];
      for (final c in items) {
        final day = _dayLabel(c.updated);
        if (day != lastDay) {
          lastDay = day;
          children.add(Padding(
            padding: const EdgeInsets.fromLTRB(4, 16, 4, 6),
            child: Text(day, style: tt.labelSmall),
          ));
        }
        children.add(Dismissible(
          key: ValueKey(c.id),
          direction: DismissDirection.endToStart,
          background: Container(
            alignment: AlignmentDirectional.centerEnd,
            padding: const EdgeInsets.symmetric(horizontal: 20),
            color: rl.danger.withValues(alpha: .12),
            child: Icon(Icons.delete_outline, color: rl.danger),
          ),
          onDismissed: (_) async {
            await History.remove(c.id);
            setState(() => items.removeWhere((x) => x.id == c.id));
          },
          child: InkWell(
            onTap: () async {
              await Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => ChatScreen(conversation: c)));
              _load();                       // maj après poursuite éventuelle
            },
            child: Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                  color: rl.surface, border: Border.all(color: rl.hairline)),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(c.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: tt.bodyLarge),
                    const SizedBox(height: 6),
                    Row(children: [
                      Icon(Icons.forum_outlined, size: 14, color: rl.meta),
                      const SizedBox(width: 5),
                      Text('${c.exchanges} ${s.messages}', style: tt.bodySmall),
                      const Spacer(),
                      Text(
                          '${c.updated.hour.toString().padLeft(2, '0')}:'
                          '${c.updated.minute.toString().padLeft(2, '0')}',
                          style: tt.labelSmall),
                    ]),
                  ]),
            ),
          ),
        ));
      }
      body = ListView(padding: const EdgeInsets.all(14), children: children);
    }

    return Scaffold(
      appBar: AppBar(title: Text(s.history)),
      body: body,
    );
  }
}
