# Chaîne qualité du corpus

Huit passes d'analyse, deux de traitement. Elles s'exécutent sur le corpus
lexical (`laws_corpus_v2.jsonl`) et n'écrivent jamais par-dessus l'original.

## Analyse — ne modifient rien

| passe | ce qu'elle cherche |
|---|---|
| `p1_structure` | champs manquants, types incohérents, plages impossibles |
| `p2_numeros` | appels de note collés aux numéros d'article |
| `p3_texte` | espaces parasites, ligatures inversées, mojibake |
| `p4b_dates_lois` | dates aberrantes dans les formules d'édiction |
| `p6_doublons` | doublons exacts, troncatures, désactivations |
| `p9_recompte` | distingue les codes réellement longs des numéros corrompus |
| `p12_alignement` | l'étiquette `article` correspond-elle à l'en-tête imprimé |
| `p13_jumeaux` | résolution par un second exemplaire du même code — **échec assumé** |
| `p14_ordre` | documents où la suite des articles recule |
| `p15_collages_courts` | collages invisibles : « 45 » = note 4 + article 5 |

## Traitement

`p10_reparer` — répare les numéros d'article. Deux méthodes indépendantes
doivent concorder (suite des articles, appel de note attesté dans le texte),
et le document n'est réparé que si sa **qualité de suite** progresse : la part
des numéros ayant un voisin immédiat. Un code numérote en continu ; c'est le
seul juge qui ne dépende d'aucune opinion.

`p11_signaler` — marque les fragments douteux sans réécrire le texte.

`p16_reparer_courts` — répare les collages courts, indiscernables à l'œil nu.
Trois preuves exigées : le retrait du préfixe restaure exactement la suite, les
préfixes retirés forment eux-mêmes une suite croissante (les notes de bas de
page se numérotent en montant), et la qualité de suite du document progresse.

## Une méthode écartée

`p13_jumeaux` cherchait à résoudre les cas douteux par un second exemplaire du
même code. Elle ne tranche que 3 cas, dont un FAUX : la loi 37.10 sur la
protection des témoins reproduit mot pour mot le texte qu'elle insère dans le
code de procédure pénale. L'identité de contenu ne prouve donc pas l'identité
de numérotation. Conservée comme trace, pas utilisée.

## Pourquoi on répare les numéros mais pas les dates

Un numéro d'article est une **étiquette** : la corriger ne touche pas au texte
du Bulletin officiel, et l'ancienne valeur est conservée dans
`article_avant_reparation`. Une date vit dans le **corps du texte** : la
réécrire ferait citer au corpus une formule que le Bulletin n'a jamais
imprimée. Le risque n'est pas symétrique, le traitement non plus.

## Garde-fous, tous nés d'une erreur constatée

- Un numéro élevé qui a des voisins est **authentique** : le code des
  obligations compte 1 250 articles, `الفصل 1000` y est légitime.
- Bornes de séquence dégénérées : on ne conclut pas.
- Étiquettes à suffixes multiples (`218-4-1`) : on ne conclut pas — l'erreur
  aurait fait dire à l'article 218-4 ce que dit le 218-1.
- Deux numéros corrompus qui convergent vers le même article : on renonce aux
  deux.
