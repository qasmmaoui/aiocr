// Client API RimLex : JWT (access + refresh rotatif), streaming NDJSON du chat.
import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class Source {
  final String law, file;
  final String? article;
  final dynamic chunk;
  Source.fromJson(Map<String, dynamic> j)
      : law = (j['law'] ?? '') as String,
        file = (j['file'] ?? '') as String,
        article = j['article']?.toString(),
        chunk = j['chunk'];
}

/// Pièce jointe à une conversation. Le serveur n'en renvoie que de quoi
/// afficher une carte — nom, nombre de pages, nature — jamais l'image des
/// pages : le fichier est effacé après cinq minutes d'inactivité, en garder
/// une reproduction lisible viderait la règle de son sens.
class Piece {
  final String id, filename, docType;
  final int nbPages;
  /// « pret », « lecture » (transcription en cours) ou « echec ».
  String etat;
  /// Avancement de la transcription, de 0 à 100.
  int progres;
  Piece.fromJson(Map<String, dynamic> j)
      : id = (j['id'] ?? '') as String,
        filename = (j['filename'] ?? '') as String,
        docType = (j['doc_type'] ?? '') as String,
        nbPages = (j['nb_pages'] ?? 0) as int,
        etat = (j['etat'] ?? 'pret') as String,
        progres = (j['progres'] ?? 0) as int;
}

class PieceError implements Exception {
  final String message;
  PieceError(this.message);
  @override
  String toString() => message;
}

class Usage {
  final String plan;
  final int used;
  final int? limit;
  Usage.fromJson(Map<String, dynamic> j)
      : plan = (j['plan'] ?? 'free') as String,
        used = (j['used'] ?? 0) as int,
        limit = j['limit'] as int?;
}

class Api {
  Api._();
  static final Api I = Api._();

  String base = const String.fromEnvironment('RIMLEX_API',
      defaultValue: 'http://10.0.2.2:8000'); // émulateur Android par défaut
  String? _access, _refresh;
  String username = '', fullname = '';
  Usage? usage;

  Future<void> init() async {
    final p = await SharedPreferences.getInstance();
    base = p.getString('base') ?? base;
    _access = p.getString('access');
    _refresh = p.getString('refresh');
    username = p.getString('username') ?? '';
    fullname = p.getString('fullname') ?? '';
    // Sur le web, l'app est servie par l'API elle-même -> même origine.
    if (Uri.base.scheme.startsWith('http') && Uri.base.host.isNotEmpty) {
      base = '${Uri.base.scheme}://${Uri.base.host}:${Uri.base.port}';
    }
  }

  bool get loggedIn => _refresh != null;

  Future<void> _save() async {
    final p = await SharedPreferences.getInstance();
    await p.setString('base', base);
    _access != null ? p.setString('access', _access!) : p.remove('access');
    _refresh != null ? p.setString('refresh', _refresh!) : p.remove('refresh');
    await p.setString('username', username);
    await p.setString('fullname', fullname);
  }

  Future<void> login(String user, String pass) async {
    final r = await http.post(Uri.parse('$base/api/mobile/auth/login'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(
            {'username': user, 'password': pass, 'device': 'flutter'}));
    if (r.statusCode != 200) throw ApiError(r.statusCode);
    final j = jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
    _access = j['access'] as String;
    _refresh = j['refresh'] as String;
    username = (j['user']?['username'] ?? '') as String;
    fullname = (j['user']?['fullname'] ?? '') as String;
    usage = Usage.fromJson((j['usage'] ?? {}) as Map<String, dynamic>);
    await _save();
  }

  Future<bool> refreshTokens() async {
    if (_refresh == null) return false;
    final r = await http.post(Uri.parse('$base/api/mobile/auth/refresh'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'refresh': _refresh, 'device': 'flutter'}));
    if (r.statusCode != 200) {
      await logout(local: true);
      return false;
    }
    final j = jsonDecode(r.body) as Map<String, dynamic>;
    _access = j['access'] as String;
    _refresh = j['refresh'] as String;
    await _save();
    return true;
  }

  Future<void> logout({bool local = false}) async {
    if (!local && _refresh != null) {
      try {
        await http.post(Uri.parse('$base/api/mobile/auth/logout'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'refresh': _refresh}));
      } catch (_) {}
    }
    _access = _refresh = null;
    username = fullname = '';
    await _save();
  }

  Future<Map<String, String>> _auth() async =>
      {if (_access != null) 'Authorization': 'Bearer $_access'};

  Future<void> me() async {
    final r = await http.get(Uri.parse('$base/api/mobile/me'),
        headers: await _auth());
    if (r.statusCode == 401 && await refreshTokens()) return me();
    if (r.statusCode == 200) {
      final j = jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
      usage = Usage.fromJson((j['usage'] ?? {}) as Map<String, dynamic>);
    }
  }

  /// Matières proposées par le serveur (clé, libellés, disponibilité).
  Future<List<Map<String, dynamic>>> matieres() async {
    try {
      final r = await http.get(Uri.parse('$base/api/matieres')).timeout(const Duration(seconds: 20));
      if (r.statusCode != 200) return [];
      final j = jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
      return ((j['matieres'] ?? []) as List)
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
    } catch (_) {
      return [];
    }
  }

  /// Joint UN document à la conversation, et rend sa fiche une fois lu.
  ///
  /// Un envoi par fichier : chaque requête reste courte, donc le délai de
  /// 100 s imposé par Cloudflare devant le proxy ne peut mordre que sur un
  /// document isolé. L'océrisation se fait pendant que l'utilisateur tape.
  /// Envois en cours, pour pouvoir les interrompre : fermer le client coupe
  /// la requête là où elle en est.
  final Map<String, http.Client> _envois = {};

  void annulerEnvoi(String cle) {
    _envois.remove(cle)?.close();
  }

  Future<Piece> joindre(String sessionId, String nom, List<int> octets,
      {String? cle}) async {
    final req = http.MultipartRequest(
        'POST', Uri.parse('$base/api/attachments?session_id=$sessionId'))
      ..headers.addAll(await _auth())
      ..files.add(http.MultipartFile.fromBytes('file', octets, filename: nom));
    final client = http.Client();
    if (cle != null) _envois[cle] = client;
    late http.Response resp;
    try {
      resp = await http.Response.fromStream(await client.send(req));
    } finally {
      if (cle != null && _envois[cle] == client) _envois.remove(cle);
      client.close();
    }
    if (resp.statusCode == 401 && await refreshTokens()) {
      return joindre(sessionId, nom, octets, cle: cle);
    }
    if (resp.statusCode != 200) {
      String detail = '';
      try {
        detail = (jsonDecode(utf8.decode(resp.bodyBytes))
            as Map<String, dynamic>)['detail']?.toString() ?? '';
      } catch (_) {}
      throw PieceError(detail.isEmpty ? 'Échec de l\'envoi' : detail);
    }
    return Piece.fromJson(
        jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>);
  }

  /// État des pièces d'une conversation — sert à savoir quand une
  /// transcription en arrière-plan est terminée.
  Future<List<Piece>> etatPieces(String sessionId) async {
    try {
      final r = await http.get(
          Uri.parse('$base/api/attachments?session_id=$sessionId'),
          headers: await _auth());
      if (r.statusCode != 200) return [];
      final j = jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
      return ((j['pieces'] ?? []) as List)
          .map((e) => Piece.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList();
    } catch (_) {
      return [];
    }
  }

  /// Retrait d'une pièce — avant l'envoi de la question, ou après coup.
  Future<void> retirerPiece(String sessionId, String id) async {
    await http.delete(
        Uri.parse('$base/api/attachments/$id?session_id=$sessionId'),
        headers: await _auth());
  }

  /// Chat en streaming NDJSON : émet d'abord les sources, puis les deltas.
  Stream<ChatEvent> ask(String question,
      {String? sessionId, String? matiere,
      List<String> attachmentIds = const []}) async* {
    var attempt = 0;
    while (true) {
      final req = http.Request('POST', Uri.parse('$base/api/chat/stream'))
        ..headers.addAll({
          'Content-Type': 'application/json',
          ...await _auth(),
        })
        ..body = jsonEncode({
          'question': question,
          'k': 6,
          if (sessionId != null) 'session_id': sessionId,
          if (matiere != null && matiere != 'all') 'matiere': matiere,
          if (attachmentIds.isNotEmpty) 'attachment_ids': attachmentIds,
        });
      final resp = await http.Client().send(req);
      if (resp.statusCode == 401 && attempt == 0 && await refreshTokens()) {
        attempt++;
        continue;
      }
      if (resp.statusCode == 429) throw QuotaError();
      if (resp.statusCode != 200) throw ApiError(resp.statusCode);
      var buf = '';
      await for (final chunk in resp.stream.transform(utf8.decoder)) {
        buf += chunk;
        final lines = buf.split('\n');
        buf = lines.removeLast();
        for (final line in lines) {
          if (line.trim().isEmpty) continue;
          final j = jsonDecode(line) as Map<String, dynamic>;
          if (j.containsKey('sources_final')) {
            // liste définitive : seules les sources réellement citées
            yield ChatEvent.sources((j['sources_final'] as List)
                .map((s) => Source.fromJson(s as Map<String, dynamic>))
                .toList());
          } else if (j.containsKey('sources')) {
            yield ChatEvent.sources((j['sources'] as List)
                .map((s) => Source.fromJson(s as Map<String, dynamic>))
                .toList());
          } else if (j.containsKey('delta')) {
            yield ChatEvent.delta(j['delta'] as String);
          } else if (j['done'] == true) {
            yield ChatEvent.done();
          }
        }
      }
      return;
    }
  }

  String viewerUrl(Source s, {bool clean = false}) =>
      '$base/api/viewer?file=${Uri.encodeComponent(s.file)}'
      '&chunk=${Uri.encodeComponent('${s.chunk ?? '-'}')}'
      '${clean ? '&clean=1' : ''}';

  String pageImageUrl(Source s, int page, {bool clean = false}) =>
      '$base/api/viewer/page-image?file=${Uri.encodeComponent(s.file)}'
      '&page=$page&chunk=${Uri.encodeComponent('${s.chunk ?? '-'}')}'
      '&clean=${clean ? 1 : 0}&v=2';

  Future<void> feedback(String type, String question, String answer,
      List<Source> sources, String comment) async {
    await http.post(Uri.parse('$base/api/feedback'),
        headers: {'Content-Type': 'application/json', ...await _auth()},
        body: jsonEncode({
          'type': type,
          'question': question,
          'answer': answer,
          'sources': [
            for (final s in sources)
              {'law': s.law, 'file': s.file, 'chunk': s.chunk}
          ],
          'comment': comment,
          'user': username.isEmpty ? 'mobile' : username,
        }));
  }
}

class ChatEvent {
  final List<Source>? sources;
  final String? delta;
  final bool done;
  ChatEvent.sources(this.sources)
      : delta = null,
        done = false;
  ChatEvent.delta(this.delta)
      : sources = null,
        done = false;
  ChatEvent.done()
      : sources = null,
        delta = null,
        done = true;
}

class ApiError implements Exception {
  final int status;
  ApiError(this.status);
}

class QuotaError implements Exception {}
