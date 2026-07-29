// عين الريم — la page originale, zoomable, passage cité surligné côté serveur,
// badge de version (محيَّن / منسوخ), navigation de pages.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../core/api.dart';
import '../core/theme.dart';
import '../main.dart';

class ViewerScreen extends StatefulWidget {
  final Source source;
  const ViewerScreen({super.key, required this.source});
  @override
  State<ViewerScreen> createState() => _ViewerScreenState();
}

class _ViewerScreenState extends State<ViewerScreen> {
  int page = 1;
  int npages = 1;
  bool clean = false;
  String status = 'current';
  String law = '';
  bool ready = false;

  @override
  void initState() {
    super.initState();
    _info();
  }

  Future<void> _info() async {
    try {
      final src = widget.source;
      final r = await http.get(Uri.parse(
          '${Api.I.base}/api/viewer/chunk-info'
          '?file=${Uri.encodeComponent(src.file)}'
          '&chunk=${Uri.encodeComponent('${src.chunk ?? '-'}')}'));
      if (r.statusCode == 200) {
        final j = jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
        page = (j['page'] ?? 1) as int;
        npages = (j['npages'] ?? 1) as int;
        status = (j['status'] ?? 'current') as String;
        law = (j['law'] ?? '') as String;
      }
    } catch (_) {}
    if (mounted) setState(() => ready = true);
  }

  Widget _badge(BuildContext context) {
    final s = AppState.of(context).s;
    final rl = context.rl;
    if (status == 'consolidated') {
      return _pill('✓ ${s.verified}', rl.primary);
    }
    if (status == 'possibly_abrogated') {
      return _pill('⛌ ${s.abrogated}', rl.danger);
    }
    return const SizedBox.shrink();
  }

  Widget _pill(String t, Color c) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
        decoration: BoxDecoration(
            color: c.withValues(alpha: .12),
            borderRadius: BorderRadius.circular(999)),
        child: Text(t, style: TextStyle(fontSize: 11.5, color: c)),
      );

  @override
  Widget build(BuildContext context) {
    final s = AppState.of(context).s;
    final rl = context.rl;
    final src = widget.source;
    final url = Api.I.pageImageUrl(src, page, clean: clean);
    return Scaffold(
      appBar: AppBar(
        title: Text(law.isNotEmpty ? law : (src.law.isEmpty ? s.viewer : src.law),
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 15)),
        actions: [
          Center(child: _badge(context)),
          IconButton(
              tooltip: clean ? s.showOriginal : s.hideWatermark,
              onPressed: () => setState(() => clean = !clean),
              icon: Icon(clean
                  ? Icons.image_outlined
                  : Icons.cleaning_services_outlined)),
        ],
      ),
      backgroundColor: rl.sunk,
      body: !ready
          ? const Center(child: CircularProgressIndicator())
          : Column(children: [
              Expanded(
                child: InteractiveViewer(
                  maxScale: 5,
                  child: Center(
                    child: Image.network(
                      url,
                      key: ValueKey(url),
                      fit: BoxFit.contain,
                      loadingBuilder: (c, w, p) => p == null
                          ? w
                          : const Center(child: CircularProgressIndicator()),
                      errorBuilder: (c, e, st) => Padding(
                        padding: const EdgeInsets.all(24),
                        child:
                            Text(s.offline, style: TextStyle(color: rl.meta)),
                      ),
                    ),
                  ),
                ),
              ),
              SafeArea(
                top: false,
                child: Container(
                  color: rl.surface,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                  child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        IconButton(
                            onPressed: page > 1
                                ? () => setState(() => page--)
                                : null,
                            icon: Icon(s.ar
                                ? Icons.chevron_right
                                : Icons.chevron_left)),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 14, vertical: 6),
                          decoration: BoxDecoration(
                              border: Border.all(color: rl.hairline),
                              borderRadius: BorderRadius.circular(999)),
                          child: Text('${s.page} $page / $npages',
                              style: TextStyle(
                                  fontFamily: kMono, color: rl.text)),
                        ),
                        IconButton(
                            onPressed: page < npages
                                ? () => setState(() => page++)
                                : null,
                            icon: Icon(s.ar
                                ? Icons.chevron_left
                                : Icons.chevron_right)),
                      ]),
                ),
              ),
            ]),
    );
  }
}
