// La gazelle RimLex — emblème géométrique + boucle «réflexion» 3 frames/420ms.
import 'dart:async';
import 'package:flutter/material.dart';

/// Emblème statique : gazelle encre, regard doré vers les documents.
class Gazelle extends StatelessWidget {
  final double size;
  final Color ink;
  final Color gold;
  final bool gaze;
  const Gazelle(
      {super.key,
      this.size = 96,
      required this.ink,
      required this.gold,
      this.gaze = true});

  @override
  Widget build(BuildContext context) => CustomPaint(
      size: Size(size, size * .78),
      painter: _GazellePainter(ink: ink, gold: gold, gaze: gaze, pose: 0));
}

/// Boucle de réflexion : 01 gather → 02 leap → 03 land, 140 ms chacune.
class GazelleThinking extends StatefulWidget {
  final double size;
  final Color ink;
  final Color leap;
  const GazelleThinking(
      {super.key, this.size = 44, required this.ink, required this.leap});

  @override
  State<GazelleThinking> createState() => _GazelleThinkingState();
}

class _GazelleThinkingState extends State<GazelleThinking> {
  int frame = 0;
  Timer? _t;

  @override
  void initState() {
    super.initState();
    _t = Timer.periodic(const Duration(milliseconds: 140),
        (_) => setState(() => frame = (frame + 1) % 3));
  }

  @override
  void dispose() {
    _t?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => CustomPaint(
      size: Size(widget.size, widget.size * .78),
      painter: _GazellePainter(
          ink: frame == 1 ? widget.leap : widget.ink,
          gold: Colors.transparent,
          gaze: false,
          pose: frame));
}

class _GazellePainter extends CustomPainter {
  final Color ink, gold;
  final bool gaze;
  final int pose; // 0 gather/debout · 1 leap · 2 land
  _GazellePainter(
      {required this.ink,
      required this.gold,
      required this.gaze,
      required this.pose});

  @override
  void paint(Canvas canvas, Size s) {
    final p = Paint()
      ..color = ink
      ..style = PaintingStyle.fill;
    final st = Paint()
      ..color = ink
      ..style = PaintingStyle.stroke
      ..strokeWidth = s.width * .045
      ..strokeCap = StrokeCap.round;
    final w = s.width, h = s.height;
    final leap = pose == 1;
    final dy = leap ? -h * .10 : 0.0;

    // corps — polygone facetté
    final body = Path()
      ..moveTo(w * .42, h * .38 + dy)
      ..lineTo(w * .78, h * .30 + dy)
      ..lineTo(w * .92, h * .42 + dy)
      ..lineTo(w * .88, h * .60 + dy)
      ..lineTo(w * .50, h * .64 + dy)
      ..lineTo(w * .40, h * .52 + dy)
      ..close();
    canvas.drawPath(body, p);
    // queue
    canvas.drawLine(
        Offset(w * .90, h * .40 + dy), Offset(w * .97, h * .32 + dy), st);
    // cou + tête
    canvas.drawLine(
        Offset(w * .46, h * .42 + dy), Offset(w * .28, h * .18 + dy), st);
    final head = Path()
      ..moveTo(w * .30, h * .12 + dy)
      ..lineTo(w * .38, h * .16 + dy)
      ..lineTo(w * .30, h * .24 + dy)
      ..lineTo(w * .17, h * .20 + dy)
      ..close();
    canvas.drawPath(head, p);
    // œil
    canvas.drawCircle(Offset(w * .285, h * .175 + dy), s.width * .022,
        Paint()..color = Colors.white);
    // cornes
    canvas.drawLine(
        Offset(w * .33, h * .12 + dy), Offset(w * .40, h * .01 + dy), st);
    canvas.drawLine(
        Offset(w * .36, h * .13 + dy), Offset(w * .46, h * .06 + dy), st);
    // pattes — trois poses
    final legs = <List<Offset>>[
      if (pose == 0) ...[
        [Offset(w * .52, h * .62), Offset(w * .50, h * .96)],
        [Offset(w * .60, h * .63), Offset(w * .62, h * .96)],
        [Offset(w * .76, h * .61), Offset(w * .74, h * .96)],
        [Offset(w * .84, h * .59), Offset(w * .88, h * .96)],
      ] else if (pose == 1) ...[
        [Offset(w * .50, h * .54), Offset(w * .30, h * .74)],
        [Offset(w * .58, h * .55), Offset(w * .40, h * .80)],
        [Offset(w * .78, h * .51), Offset(w * .94, h * .68)],
        [Offset(w * .86, h * .49), Offset(w * 1.0, h * .60)],
      ] else ...[
        [Offset(w * .52, h * .62), Offset(w * .44, h * .96)],
        [Offset(w * .60, h * .63), Offset(w * .58, h * .92)],
        [Offset(w * .78, h * .61), Offset(w * .82, h * .92)],
        [Offset(w * .86, h * .59), Offset(w * .94, h * .96)],
      ]
    ];
    for (final l in legs) {
      canvas.drawLine(Offset(l[0].dx, l[0].dy + dy),
          Offset(l[1].dx, l[1].dy + dy), st);
    }
    // le regard doré (عين الريم)
    if (gaze) {
      final g = Paint()
        ..color = gold
        ..strokeWidth = s.width * .018
        ..strokeCap = StrokeCap.round;
      canvas.drawLine(Offset(w * .27, h * .19), Offset(w * .04, h * .52), g);
      canvas.drawLine(Offset(w * .27, h * .21), Offset(w * .10, h * .62), g);
    }
  }

  @override
  bool shouldRepaint(_GazellePainter o) =>
      o.pose != pose || o.ink != ink || o.gaze != gaze;
}
