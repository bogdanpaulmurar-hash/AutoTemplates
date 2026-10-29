# TESTING — AutoTemplates

Pași de test pentru versiunile netestate pe Windows. Ce a fost confirmat (✅ în vechiul document) a fost scos. După confirmare, șterge pașii de aici și notează în CHANGELOG.md.

## Actualizare înainte de test
Închizi AutoTemplates din tray (Ieșire). În clona locală: `git pull`, apoi `Install.bat` (reinstalează codul și repornește aplicația). Opțional `pytest`. La 0.3.0 (pywin32 nou) reinstalarea e obligatorie. Versiunea apare în Setări › Despre.

## Unreleased — OneNote subpagină și NoteIT (netestat pe Windows)
1. NoteIT → Trimite OneNote: apare arborele caiet / secțiune / pagină. Alege o secțiune: pagină nouă la sfârșit.
2. Alege o pagină existentă: nota apare ca subpagină imediat sub ea.
3. Fără OneNote desktop: nota e în clipboard și mesajul arată motivul (copiază-l dacă apare pe laptopul de serviciu).
4. Ctrl+Shift+D inserează data și ora; Ctrl+Shift+Enter copiază ca text simplu.

## 0.3.6 — NoteIT: renunță la notă (în main, netestat) — (26.10)
- Lipești în NoteIT un text cu fundal colorat; „Curăță formatarea” (meniul butonului X) scoate fundalul.
- Butonul coș (sau Ctrl+Shift+Del) cere confirmare și golește nota fără s-o păstreze ca Ultima notă; închizi și redeschizi NoteIT: e goală.
- „Notă nouă” cu text scris întreabă: Păstrează ca Ultima notă / Renunță / Anulează.

## 0.3.0 — Office și NoteIT
- Ctrl+Alt+Q → meniu → Template: se lipește în aplicația din care ai apăsat?
- Ctrl+Alt+N → notă cu o captură → Salvează în Notes/Ședințe: apare ca template, cu poza?
- Trimite Email: mail Outlook cu formatare, poză inline și semnătură.
- Trimite OneNote: lista de notebook-uri și secțiuni, pagina se creează cu poza (OneNote din Store nu are COM: nota ajunge doar în clipboard).
- Închizi NoteIT cu X și redeschizi: ciorna e acolo; după Copiază & Închide, „Ultima notă” o readuce.

## Formatare (23.10)
- Ctrl+B / I / U / Shift+X se aplică și se scot; selecție parțial îngroșată + Ctrl+B: devine toată îngroșată.
- Ctrl+Shift+L / O (liste), Ctrl+M / Shift+M (indent), Ctrl+Alt+1/2/3 (titlu), Ctrl+Shift+N (normal), Ctrl+L/E/R/J (aliniere), Ctrl+K (link).
- AltGr: ă, î, ș, ț se scriu normal, fără să schimbe stilul.
- Text formatat din web/Word + Ctrl+Space sau „Curăță”: dispar stilurile, rămân pozele și linkurile; meniul butonului: „Curăță tot documentul”, „Lipire ca text simplu”.
- Imagine: click → chenar albastru; tragi de colț → redimensionare proporțională; dublu-click → dialog de mărime.
- NoteIT: aceleași scurtături, tooltip-uri cu tasta, buton „Redimensionează imaginea”; tooltip-urile în română; Ctrl+S / N / F ca înainte.

## Arbore editor (24.10)
- Drag & drop: template pe alt folder; folder pe folder și pe spațiul gol (rădăcina). Favoritele (★) și pozele rămân.
- Drag nepermis: folder în subfolderul lui; nu se poate trage cu filtru activ.
- Click dreapta pe folder: Redenumește (inclusiv doar litere mari/mici), Mută în….
- Conflict de nume la mutare: Combină / Păstrează ambele / Anulează; la Combină, fișierele identice devin „Nume (2)”.
- Ștergere folder: confirmare cu numărul de template-uri și subfoldere; ajunge în Coș; pe G: dacă Coșul refuză, întreabă înainte de ștergerea definitivă. Restaurarea din Coș readuce utilizările și favoritele. Setări › Inserare: „Păstrează statisticile template-urilor șterse (zile)” (implicit 30).
- Template deschis într-un folder mutat rămâne deschis la noua cale; NoteIT salvează în noua locație dacă muți folderul lui.

## 0.3.1 — format la inserare (24.10)
- Setări › Inserare: „Text fără font propriu”, „Pozele din template-uri”, bifa Outlook/Word (implicit: fontul editorului, Automat, bifat).
- Outlook, mail nou, cursor în corp: template .html cu bold, culori, listă, poză; formatarea și fontul rămân. În Subiect: se lipește normal.
- Word: .docx cu titluri, listă numerotată pe 2 niveluri, tabel, poză; fonturile documentului, numerotare 1 / a.
- Word › Opțiuni › Complex › „Păstrează doar textul”: formatarea rămâne; debifat în AutoTemplates: vine doar text. La final revii la setarea ta.
- .rtf: în Word/Outlook identic cu poze; în Teams/browser cu bold, culori, mărimi. .md în Teams/browser: titlu și bold rămân.
- Poze în Teams și browser: la calitatea originală (Teams poate elimina fontul ales). Cod colorat (.py) în Outlook și Teams: culorile rămân. Shift+Enter: text simplu. NoteIT → Copiază & Închide → Ctrl+V în Outlook: formatarea rămâne.
- Dacă ceva nu merge: aplicația, tipul fișierului și ce s-a pierdut; în log apare „COM paste not used” când lipirea prin COM nu s-a folosit.

## 0.3.2 — backup (24.10)
- Setări › Backup: implicit `Documents\AutoTemplates Backups`, „Zilnic”, 10 copii, template-urile nebifate; „Răsfoiește…”.
- Folder în Google Drive / OneDrive (opțional): se scrie fără eroare; dacă sincronizarea blochează, „Backup-ul nu a reușit” în tray.
- Restaurare pe același calculator: faci backup, schimbi tema, scoți un favorit, scrii în ciornă, apoi Restaurează…. Previzualizarea arată ce diferă; după restaurare revin tema, favoritul, ciorna; rezumat cu numele backup-ului de siguranță (`…-before-restore.zip`).
- Statistici: „Combină” păstrează utilizările mai mari și favoritele din ambele; „Înlocuiește complet” le ia din backup.
- Template-uri: modifici un template și restaurezi cu bifa Template-uri: originalul rămâne, cel din backup vine „Nume (2)” (cu poza dacă e .html); cele identice se sar.
- Alt calculator / altă locație: restaurezi un backup de pe celălalt laptop. Apare „Păstrează biblioteca actuală” (implicit); locația bibliotecii, folderul de backup și pornirea cu Windows rămân locale; pozele din ciornă se văd.
- Fișier greșit (.zip oarecare): mesaj clar, fără modificări.

## 0.3.3 / 0.3.5 — grupuri în picker (24.10)
- 0.3.5: Ctrl+Alt+Q deschide lista (0.3.4 cădea la deschidere).
- Lista grupată: ★ Favorite și Recente (ultimele 5) sus, apoi câte un antet pe folder cu numărul de template-uri; rădăcina la „Fără folder”, primul.
- ↑/↓ sar peste antete; ← pliază grupul (antet cu ▸); → / Enter îl deschide; click pe antet pliază; Ctrl+↑/↓ sare la grupul anterior/următor; grupurile pliate se țin minte și după repornire.
- Căutare: rămân doar grupurile cu rezultate, deschise, Recente dispare; golirea readuce grupurile pliate.
- Alt+1…9 sar peste antete. Ctrl+D pe un template îl adaugă imediat la ★ Favorite. Ctrl+G sau butonul folder comută la lista simplă și înapoi (alegerea se păstrează).
- Filtru pe un folder sau pe ★: Favorite și Recente dispar. Setări › Inserare: „Vizualizare în picker”, „Template-uri în grupul Recente” (0 = dispare), „Favoritele apar și în folderul lor”.

## 0.3.4 — ghid de utilizare (24.10)
- F1 din picker (se închide, ghidul se deschide la Picker cu tasta ta reală), din editor (secțiunea Editor, butonul „?”), din NoteIT (ghidul apare deasupra), din meniul rapid și din Setări (ghidul rămâne utilizabil cât timp Setările sunt deschise). Tray › „Ghid de utilizare” deschide ultima secțiune văzută.
- Căutare „restaurare”: rămân Setări, Backup și restaurare, Probleme frecvente, cu cuvântul marcat; cuvânt inexistent: „Nimic găsit în ghid.”; Ctrl+F duce în căutare.
- Ghidul reflectă tasta schimbată și „Recente = 0”; în English e în engleză; lizibil în dark și light; DevPilot › „User guide” îl deschide.
