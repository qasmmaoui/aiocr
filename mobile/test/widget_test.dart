import 'package:flutter_test/flutter_test.dart';
import 'package:rimlex_mobile/main.dart';

void main() {
  testWidgets('RimLex demarre sur le splash (gazelle + marque)',
      (tester) async {
    await tester.pumpWidget(const RimLexApp());
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('RimLex'), findsOneWidget);
  });
}
