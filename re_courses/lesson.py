import re
r"""
regular expression

=== 1. Quantificateurs (combien de fois ?) ===
*	0 ou plus	ab*	a, ab, abbb
+	1 ou plus	ab+	ab, abbb (pas « a »)
?	0 ou 1 (optionnel)	colou?r	color, colour
{n}	exactement n fois	\d{4}	2026
{n,}	au moins n fois	\d{2,}	12, 123…
{n,m}	entre n et m fois	\d{2,4}	12, 123, 1234
*? +? ??	version paresseuse (le minimum)	<.+?>	« <a> » dans « <a><b> »

=== 2. Métacaractères de base ===
.	n’importe quel caractère (sauf \n)	c.t	« cat », « c9t » (pas « ct », pas « chat »)
^	début de la chaîne	^Bonjour	« Bonjour toi »
$	fin de la chaîne	\.py$	« lesson.py »
\	échappe un caractère spécial	\.	un vrai point « . »
|	OU	chat|chien	« chat » ou « chien »
( )	groupe (capture)	(ab)+	« abab »
[ ]	ensemble de caractères	[aeiou]	une voyelle

=== 3. Classes de caractères (MAJUSCULE = inverse) ===
\d	un chiffre [0-9]	\d+	« 2026 »
\D	tout sauf un chiffre	\D+	« abc »
\w	lettre, chiffre ou _	\w+	« mot_1 »
\W	tout sauf \w	\W	« ! », « - », « »
\s	espace, tabulation, \n	\s+	« »
\S	tout sauf un espace	\S+	« mot »
\b	frontière de mot	\bchat\b	« chat » (pas « chaton »)
\B	pas une frontière de mot	\Bton	« ton » dans « chaton »

=== 4. Ensembles [ ] ===
[abc]	a, b ou c	[abc]	« a »
[a-z]	une lettre minuscule	[a-z]+	« bonjour »
[A-Za-z0-9]	lettre ou chiffre	[A-Za-z0-9]+	« Py3 »
[^abc]	tout SAUF a, b, c (^ au début du crochet = négation)	[^0-9]+	« abc »
[.?*]	dans [ ] les caractères spéciaux sont littéraux	[.?]	« . » ou « ? »

=== 5. Groupes ===
(...)	groupe capturant → .group(1)	(\d{4})-(\d{2})	« 2026 », « 10 »
(?:...)	groupe NON capturant	(?:ab)+	« abab »
(?P<nom>...)	groupe nommé → .group('nom')	(?P<annee>\d{4})	« 2026 »
\1	répète ce que le groupe 1 a trouvé	(\w)\1	« ll » dans « hello »

=== 6. Fonctions du module re ===
re.match(p, s)	au DÉBUT de la chaîne seulement
re.search(p, s)	première occurrence n’importe où
re.fullmatch(p, s)	TOUTE la chaîne doit correspondre
re.findall(p, s)	liste de toutes les occurrences
re.finditer(p, s)	itérateur d’objets Match
re.sub(p, r, s)	remplace les occurrences
re.split(p, s)	découpe la chaîne
re.compile(p)	prépare une regex réutilisable

"""


text = """
M123456,hanine,2006,l.hanine@gmail.com
MN789123,yassine,2004,a.yassine@esisa.ac.ma
"""
pattern = re.compile(r'(.*),(.*),(?P<date>\d{4})')

match = re.search(pattern, text)

# match = re.search(r'(.*,)(.*,)(?P<date>\d{4})', text)
""" if match:
    print(match.groupdict(3), match.start(), match.end()) """


# findall vs finditer
""" results = re.findall(pattern, text)
for match in results:
    print(match[0], match[2]) """


matches = re.finditer(pattern, text)
for match in matches:
    print(match.group(1), match.group(2))
