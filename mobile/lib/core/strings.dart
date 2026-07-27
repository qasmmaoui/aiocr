// i18n RimLex — arabe (défaut, RTL) et français.
import 'package:flutter/widgets.dart';

class S {
  final String locale;
  const S(this.locale);
  bool get ar => locale == 'ar';
  TextDirection get dir => ar ? TextDirection.rtl : TextDirection.ltr;

  String get appName => ar ? 'ريم لكس' : 'RimLex';
  String get tagline => ar ? 'الإدارة بالحجة' : "La preuve d'abord";
  String get login => ar ? 'تسجيل الدخول' : 'Se connecter';
  String get username => ar ? 'اسم المستعمل' : "Nom d'utilisateur";
  String get password => ar ? 'كلمة السر' : 'Mot de passe';
  String get loginFailed =>
      ar ? 'بيانات الدخول غير صحيحة.' : 'Identifiants incorrects.';
  String get askHint =>
      ar ? 'اكتب سؤالك القانوني…' : 'Posez votre question juridique…';
  String get thinking =>
      ar ? 'جارٍ البحث في المدونة القانونية…' : 'Recherche dans le corpus…';
  String get sources => ar ? 'المصادر' : 'Sources';
  String get correct => ar ? 'صحيح' : 'Exact';
  String get wrong => ar ? 'خطأ' : 'Faux';
  String get contest => ar ? 'أعترض' : 'Contester';
  String get contestHint => ar
      ? 'ما وجه الاعتراض؟ اذكر سندك القانوني إن أمكن…'
      : "Motif de l'objection — citez votre base légale si possible…";
  String get contestSend =>
      ar ? 'إرسال الاعتراض' : "Envoyer l'objection";
  String get contestDone => ar
      ? 'أُحيل اعتراضك على فريق المراجعة — شكراً.'
      : 'Objection transmise à la revue — merci.';
  String get feedbackDone => ar ? 'سُجِّلت ملاحظتك' : 'Retour enregistré';
  String get emptyTitle =>
      ar ? 'اسأل، واقرأ القانون بعينك' : 'Demandez, et lisez la loi vous-même';
  String get emptyBody => ar
      ? 'كل جواب يفتح الصفحة الأصلية مع تظليل المقتطف المُحال عليه.'
      : "Chaque réponse ouvre la page originale, passage cité surligné.";
  List<String> get starters => ar
      ? [
          'ما مدة الحضانة في مدونة الأسرة؟',
          'شروط تنفيذ حكم أجنبي بالمغرب',
          'آجال الطعن بالنقض في المادة التجارية'
        ]
      : [
          'Durée de la garde (hadana) dans le Code de la famille ?',
          "Conditions d'exequatur d'un jugement étranger",
          'Délais du pourvoi en cassation en matière commerciale'
        ];
  String get offline =>
      ar ? 'الخدمة غير متاحة حالياً' : 'Service momentanément indisponible';
  String get retry => ar ? 'إعادة المحاولة' : 'Réessayer';
  String get history => ar ? 'المحفوظات' : 'Historique';
  String get settings => ar ? 'الإعدادات' : 'Réglages';
  String get language => ar ? 'اللغة' : 'Langue';
  String get theme => ar ? 'المظهر' : 'Thème';
  String get themeLight => ar ? 'فاتح' : 'Clair';
  String get themeDark => ar ? 'داكن' : 'Sombre';
  String get themeSystem => ar ? 'النظام' : 'Système';
  String get logout => ar ? 'تسجيل الخروج' : 'Déconnexion';
  String get viewer => ar ? 'عين الريم' : "L'œil de Rim";
  String get page => ar ? 'ص' : 'p.';
  String get hideWatermark =>
      ar ? 'إخفاء العلامة المائية' : 'Masquer le filigrane';
  String get showOriginal => ar ? 'عرض الأصل' : "Voir l'original";
  String get extractedText => ar ? 'النص المستخرَج' : 'Texte extrait';
  String get citedPassage =>
      ar ? 'المقتطف المُحال عليه' : 'Passage cité';
  String usageOf(int used, int limit) => ar
      ? '$used / $limit سؤالاً هذا الشهر'
      : '$used / $limit questions ce mois';
  String get unlimited => ar ? 'بلا حدود' : 'Illimité';
  String get quotaReached => ar
      ? 'بلغت حدّ خطتك لهذا الشهر — قم بالترقية للمتابعة.'
      : 'Quota mensuel atteint — passez au plan supérieur.';
  String get plans => ar ? 'الخطط' : 'Offres';
  String get disclaimer => ar
      ? 'أداة مساعدة للبحث — النص الأصلي وحده هو الحجة.'
      : "Outil d'aide à la recherche — seul le texte original fait foi.";
  String get verified => ar ? 'محيَّن' : 'À jour';
  String get abrogated => ar ? 'منسوخ' : 'Abrogé';
  String get today => ar ? 'اليوم' : "Aujourd'hui";
  String get yesterday => ar ? 'أمس' : 'Hier';
  String get newChat => ar ? 'محادثة جديدة' : 'Nouvelle conversation';
  String get serverUrl => ar ? 'عنوان الخادم' : 'Adresse du serveur';
  String get genFailed => ar
      ? 'تعذّر إتمام الجواب — أعد المحاولة'
      : 'Réponse interrompue — réessayez';
}
