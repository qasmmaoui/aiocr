// Historique des conversations : sauvegarde locale complète (questions,
// réponses, sources) pour rouvrir une discussion et la poursuivre.
import 'dart:convert';
import 'dart:math';

import 'package:shared_preferences/shared_preferences.dart';

class StoredMessage {
  final bool me;
  final String text;
  final List<Map<String, dynamic>> sources;
  const StoredMessage(this.me, this.text, this.sources);

  Map<String, dynamic> toJson() =>
      {'me': me, 'text': text, 'sources': sources};

  static StoredMessage fromJson(Map<String, dynamic> j) => StoredMessage(
        j['me'] == true,
        (j['text'] ?? '') as String,
        ((j['sources'] ?? []) as List)
            .map((e) => Map<String, dynamic>.from(e as Map))
            .toList(),
      );
}

class Conversation {
  final String id;
  String title;
  DateTime updated;
  List<StoredMessage> messages;

  Conversation({
    required this.id,
    required this.title,
    required this.updated,
    required this.messages,
  });

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'updated': updated.toIso8601String(),
        'messages': messages.map((m) => m.toJson()).toList(),
      };

  static Conversation fromJson(Map<String, dynamic> j) => Conversation(
        id: (j['id'] ?? '') as String,
        title: (j['title'] ?? '') as String,
        updated:
            DateTime.tryParse((j['updated'] ?? '') as String) ?? DateTime.now(),
        messages: ((j['messages'] ?? []) as List)
            .map((e) => StoredMessage.fromJson(Map<String, dynamic>.from(e as Map)))
            .toList(),
      );

  int get exchanges => messages.where((m) => m.me).length;
}

/// Stockage : une clé unique contenant la liste des conversations
/// (les 50 plus récentes — au-delà, l'historique serveur prendra le relais).
class History {
  static const _key = 'conversations_v1';
  static const _max = 50;

  static Future<List<Conversation>> all() async {
    final p = await SharedPreferences.getInstance();
    try {
      final raw = jsonDecode(p.getString(_key) ?? '[]') as List;
      final list = raw
          .map((e) => Conversation.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList();
      list.sort((a, b) => b.updated.compareTo(a.updated));
      return list;
    } catch (_) {
      return [];
    }
  }

  static Future<void> save(Conversation c) async {
    final list = await all();
    list.removeWhere((x) => x.id == c.id);
    c.updated = DateTime.now();
    list.insert(0, c);
    final p = await SharedPreferences.getInstance();
    await p.setString(
        _key, jsonEncode(list.take(_max).map((x) => x.toJson()).toList()));
  }

  static Future<void> remove(String id) async {
    final list = await all()
      ..removeWhere((x) => x.id == id);
    final p = await SharedPreferences.getInstance();
    await p.setString(_key, jsonEncode(list.map((x) => x.toJson()).toList()));
  }

  static final _alea = Random.secure();

  /// Identifiant de conversation — tiré au hasard, pas dérivé de l'heure.
  ///
  /// C'était l'horodatage en microsecondes : une valeur énumérable. Or le
  /// serveur accepte tel quel l'identifiant qu'on lui donne, et une
  /// conversation porte la mémoire du dossier et le texte des pièces jointes.
  /// Deviner un identifiant, c'est lire le dossier d'un confrère.
  static String newId() {
    final o = List<int>.generate(16, (_) => _alea.nextInt(256));
    return o.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  }

  /// Titre = début de la première question, tronqué proprement.
  static String titleFrom(String firstQuestion) {
    final t = firstQuestion.trim().replaceAll(RegExp(r'\s+'), ' ');
    return t.length <= 60 ? t : '${t.substring(0, 60)}…';
  }
}
