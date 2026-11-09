# Руководство 1.2: что было в ревью, что сделано и как это повторять

Документ-инструкция: для каждого из 14 пунктов ревью — **замечание → решение →
что именно поменялось в коде → как проверить**. Плюс отдельный раздел про
сломанный файл и про то, как теперь ловится эта ошибка.

Состояние на момент написания:

| Что | Значение |
|---|---|
| Ветка | `arena/2f9949bf-mark`, HEAD `8ef55f9` |
| Исходник | `src/MARSHDWG.lsp` — UTF-8/LF, 732 строки, 90 форм, 53 `defun` |
| Рабочий файл | `dist/MARSHDWG.lsp` — CP1251/CRLF без BOM, 28 128 б, sha256 `c21d1422…` |
| Версия | `*md:rev*` = `Ред. 1.1` |
| Тесты | `build.py` → `structure.py` → `test_lisp_logic.py` — все `ИТОГ: OK` |
| Раздатчик | архив не нужен: `dist/MARSHDWG.lsp` лежит в репозитории |

---

## 0. Сначала — авария, из-за которой пришлось откатываться

### Что случилось

Я правил `src/MARSHDWG.lsp` точечными заменами и в трёх местах сбил число
закрывающих скобок. `tests/lisp_parse.py` при этом вёл себя обманчиво:

* иногда падал `KeyError: 'md:mark-color'` — из `test_lisp_logic.py`;
* иногда `structure.py` писал `ИТОГ: OK`, хотя `defun`-ов было 48 вместо 50.

Причина: незакрытая форма в `md:do-text` «проглатывала» следующие определения
(`md:do-grid`, `md:do-dim`, …). Для парсера это синтаксически валидное дерево —
`defun` просто оказывается вложенным в предыдущий, а не верхнеуровневым. Итоговый
`dist` в таком виде отгружать было нельзя.

### Как вылечил

1. `git checkout 5b73119 -- src/MARSHDWG.lsp` — вернул **заведомо
   сбалансированную** версию (50 `defun`, `lisp_parse` без ошибок).
2. Заново применил правки, но уже **блоками**, и после каждого блока гонял
   `lisp_parse.check`. Блок упал на ассерте — файл не записался, ничего не
   потерялось. Так правки 1–4 не пропали, а просто применились вторым заходом.
3. Финальная проверка — построчный счётчик скобок: глубина в конце файла `0`,
   ни один `(defun` не начинается при глубине ≠ 0.

### Как теперь это ловится автоматически

Проверка встроена в `tests/structure.py` (блок перед подсчётом функций):

```python
depth = 0
swallowed = []
for no, line in enumerate(src.split("\n"), 1):
    code = line if not line.lstrip().startswith(";") else ""
    if line.lstrip().startswith("(defun") and depth != 0:
        swallowed.append((no, depth))
    in_str = False
    for ch in code:
        if ch == '"':
            in_str = not in_str
        elif in_str:
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
if swallowed or depth != 0:
    print("FAIL проглоченные defun:", swallowed, "| глубина в конце:", depth)
    ok = False
```

Проверено намеренной поломкой (убрал одну `)` в `md:do-grid`):

```text
FAIL проглоченные defun: [(309, 1), (329, 1), (342, 1), …] | глубина в конце: 1
```

### Правило на будущее

1. Перед любой правкой: `cd /home/user/MarshDWD && git log --oneline -3 && git status`.
   Песочница откатывает рабочее дерево — работать только от `origin`.
2. Правки — только скриптом с `assert old in s` (нет совпадения → падение, файл
   не записан). Никаких «на глаз» правок скобок в редакторе.
3. После каждого смыслового блока — `lisp_parse.check`, после всех — `build.py` +
   оба теста.
4. Смотреть на **число `defun`**, а не только на `ИТОГ: OK`: ожидается 53.

---

## 1–14. Пункты ревью: замечание → решение

### п.4 — выключение слоёв не должно быть «заморозкой»

**Замечание.** Ревьюер: выключить слой ≠ заморозить; `VP Freeze` на видовых
экранах трогать нельзя.

**Решение.** Только `LayerOn`. Заморозка (`Freeze`), `VP Freeze`, `Lock` не
меняются вообще — к ним в коде нет ни одного `vla-put`. Уже выключенный слой не
считается изменением.

```lisp
(defun md:do-layers (dbx / lays name lay)
  …
  (foreach name *md:off-layers*
    (setq lay (md:item lays name))
    (cond
      ((null lay) (md:warn (strcat "слой не найден: " name)))
      ((md:on-p (md:try 'vla-get-LayerOn lay nil))          ; включён?
       (if (md:try-set 'vla-put-LayerOn lay :vlax-false)     ; выключаем
         (md:bump "layers-off")))))
  …)
```

**Осознанное дополнение в README.** Объекты **внутри блоков** на выключенном
слое всё равно проходят остальные правила (цвет/высота). Это оставлено: слой
убирает видимость в модели, а правка свойств невидимых объектов безопасна. Если
заказчик скажет «такие объекты не трогать» — добавляется фильтр `md:layer-on-p`
в `md:do-obj`.

**Как проверить.** `СЛОЙ` → 10 слоёв выключены (лампочка жёлтая), заморозка
(солнце/снежинка) не изменилась. Повторный прогон: счётчик `слоёв выкл.: 0`.

---

### п.6 — не обрабатывались листы (Layout)

**Замечание.** Правила применялись только к модели; на листах оставались старые
цвета и высоты.

**Решение.** Новый параметр и новая функция; вызов в `md:run-one` под флагом.
По умолчанию **выключено** — чтобы пилотный прогон не менял оформление листов
неожиданно.

```lisp
(setq *md:scan-paperspace* nil)   ; t = обрабатывать и листы (Layout)

(defun md:scan-paperspace (dbx / lays lay ps tno)
  (setq lays (md:try 'vla-get-Layouts dbx nil))
  (if lays
    (vlax-for lay lays
      (setq tno (md:try 'vla-get-TabOrder lay nil))
      ;; TabOrder 0 — модель; если свойство недоступно, лист всё равно проверим.
      (if (or (not (numberp tno)) (> tno 0))
        (progn
          (setq ps (md:try 'vla-get-Block lay nil))
          (if ps (md:scan-space ps)))))))
```

В `md:run-one`:

```lisp
(md:scan-space (md:try 'vla-get-ModelSpace tgt nil))
(if *md:scan-paperspace* (md:scan-paperspace tgt))
(md:scan-blocks tgt)
```

**Как проверить.** `(setq *md:scan-paperspace* t)`, прогнать один файл, в
журнале счётчики вырастут; открыть лист — тексты/цвета обновлены.

---

### п.12 — счётчики врали

**Замечание.** Отчёт показывал «обработано N», даже если значения уже стояли
правильные; повторный прогон выглядел как «всё переделано заново».

**Решение.** Все функции изменения возвращают `t`/`nil` — «реально изменил», и
счётчик растёт только по `t`.

```lisp
(defun md:set-h (o h / cur done)
  (if (and (vlax-property-available-p o 'Height t)
           (not (equal (setq cur (md:try 'vla-get-Height o nil)) h 1e-6)))
    (progn
      (setq done (md:try-set 'vla-put-Height o h))
      (if done (md:bump "height") (md:bump "locked"))
      done)))
```

`md:set-color` — так же. Дальше по цепочке:

```lisp
(defun md:do-grid (o)
  (if (md:set-color o *md:grid-color*) (md:bump "grid")))

(defun md:do-text (o / lay txt col chg)
  …
    ((md:in-list lay *md:dim-layers*)
     (if (md:set-h o *md:dim-height*) (md:bump "dim-text"))
     (md:bg-off o))
    ((md:in-list lay *md:prod-layers*)
     (setq chg nil)
     (if (md:set-h o *md:prod-height*) (setq chg t))
     (if (md:bg-off o) (setq chg t))
     (setq txt (md:try 'vla-get-TextString o nil))
     (setq col (md:mark-color txt))
     (if (null col) (setq col (md:layer-default lay)))
     (if (and col (md:set-color o col)) (setq chg t))
     (if chg (md:bump "prod"))))
```

Штриховка: если у фона уже `ColorMethod = 0` («Нет»), ничего не пишем и счётчик
не растём.

```lisp
(setq c (md:try 'vla-get-BackgroundColor o nil))
(if (and c (= (md:try 'vla-get-ColorMethod c nil) 0))
  nil                                  ; фон уже «Нет»
  (progn … (md:bump "hatch")))
```

**Как проверить.** Прогнать один и тот же файл дважды. Второй прогон:
`слоёв выкл.: 0, серых: 0, марок осей: 0 … вставок: 0`. Это и есть приёмочный
признак «правила применены».

---

### п.13 — `BackgroundFill` сравнивался через `eq :vlax-true`

**Замечание.** Разные версии AutoCAD отдают `:vlax-true`, `1`, `-1`; `eq` даёт
ложное «не включено», маска остаётся.

**Решение.** Один предикат на весь файл:

```lisp
;; «Включено» для :vlax-true / 1 / -1, «выключено» для nil / 0 / :vlax-false.
(defun md:on-p (v)
  (cond ((null v) nil)
        ((eq v :vlax-false) nil)
        ((eq v :vlax-true) t)
        ((numberp v) (/= v 0))
        (t t)))

(defun md:bg-off (o / cur)
  (cond
    ((not (vlax-property-available-p o 'BackgroundFill t)) nil)
    ((md:on-p (setq cur (md:try 'vla-get-BackgroundFill o nil)))
     (if (md:try-set 'vla-put-BackgroundFill o :vlax-false)
       (progn (md:bump "bg-off") t)))))
```

Через `md:on-p` работает и проверка `LayerOn` в п.4 — один источник истины.

**Как проверить.** На тексте с маской: `СВОЙСТВА` → «Фон: нет»; повторный
прогон — `масок: 0`.

---

### п.14 — резервная копия не гарантирована

**Замечание.** Если `vl-file-copy` падал, файл всё равно открывался и
пересохранялся — без возможности откатиться.

**Решение.** Флаг + ранний выход. Без копии файл **не открывается вообще**.

```lisp
(setq *md:require-backup* t)   ; t = без копии файл не обрабатывается

;; в md:run-one
(setq ok t)
(if (not (md:backup path))
  (progn (md:warn "файл пропущен: нет резервной копии") (setq ok nil)))
(if ok
  (progn
    (setq tgt (md:dbx-open path))
    (setq src (md:dbx-open srcpath))
    (setq *md:dbx* tgt)))
(cond
  ((not ok) nil)
  ((or (null tgt) (null src)) (md:warn "файл не открыт — пропуск") (setq ok nil))
  (t …))
```

**Как проверить.** Сделать папку `MARSHDWG_BACKUP` только для чтения → в журнале
`[ПРОПУСК]` и файл не меняется.

---

### п.11 — `*md:recurse*` объявлен, но не работал

**Замечание.** Параметр есть, поведение не реализовано: `vl-directory-files … 1`
не обходит подпапки.

**Решение.** `md:collect` — рекурсивный сбор, и `c:MARSHDWG` работает уже с
полными путями (раньше склеивал `folder\name` повторно).

```lisp
(setq *md:recurse* nil)   ; t = обходить вложенные папки

(defun md:collect (folder / files name sub res)
  (setq files (vl-directory-files folder "*.dwg" 1))
  (setq res nil)
  (foreach name files
    (setq res (append res (list (strcat folder "\\" name)))))
  (if *md:recurse*
    (foreach sub (vl-directory-files folder "*.*" -1)
      (if (and (not (member sub (list "." "..")))
               (vl-file-directory-p (strcat folder "\\" sub)))
        (setq res (append res (md:collect (strcat folder "\\" sub)))))))
  res)
```

```lisp
(setq files (md:collect folder))
…
(foreach path files
  (if (md:run-one path src) (setq k (1+ k))))
```

**Как проверить.** `(setq *md:recurse* t)` → в журнале «файлов: N» больше, чем
файлов в корне.

---

### п.5 — `S-GRID-IDEN` в двух правилах

**Замечание.** Слой одновременно в «серые 251» и в «марки осей красные».

**Ответ: так и задумано.** Порядок правил фиксирован, противоречия нет:

1. слой `S-GRID-IDEN` получает цвет 251 — это цвет для прочих объектов слоя;
2. объекты слоя (марки осей, включая содержимое блоков) получают красный 1.

Проверка: `СЛОЙ` → `S-GRID-IDEN` цвет 251; выбрать марку оси → `СВОЙСТВА` →
цвет «Красный». Ничего не менял.

---

### п.8 — откуда цвета 1/5/2/4/3/200

**Ответ.** Единственный источник — блок `*md:mark-colors*` и таблица в README:

| Шаблон | Что | Цвет |
|---|---|---|
| `*EI*` | EI | 1 красный |
| `Д*` | двери (ДВ, ДГ, ДС, ДСВ, ДН, ДПВ) | 5 синий |
| `ОК*` | окна | 2 жёлтый |
| `ББ*`, `Б*` | балконные блоки / балконы | 2 жёлтый |
| `ОЛ*` | лоджии | 4 голубой |
| `ВТ*` | витражи | 3 зелёный |

Плюс «цвет по слою», если символ не подошёл: `A-GLAZ-IDEN` → 2, `A-DOOR-IDEN` →
5, `A-WALL-IDEN` → 3. **Требует подтверждения заказчика** — это единственный
пункт, где я не могу проверить цифры по исходным данным.

---

### п.9 — высота текста блока «Марка этажа» 2400

**Ответ.** Масштаб вставки остаётся `1.0` (так в ТЗ: 1:1), высота текста блока
остаётся исходной 2400. Если нужно подогнать под H = 250:

```lisp
(setq *md:ins-scale* 0.104)   ; 250 / 2400 ≈ 0.1042
```

Либо точнее — через высоту атрибута, не трогая масштаб:

```lisp
(setq *md:attr-height* 250.0)   ; подгоняет только текст атрибута «Этаж»
```

**Открытый вопрос заказчику:** 2400 или 250?

---

### п.10 — формат атрибута «Этаж»

**Ответ.** Берётся хвост имени после последнего `ОП` **как есть**, кавычки не
пишутся: `7.2 ОП1.dwg` → `1`, `Объект ОП-1.dwg` → `-1`. Если перед `ОП` стоит
буква/цифра (`ПОП1`) или после `ОП` пусто — блок не вставляется, в журнале
`[ПРОПУСК] в имени файла нет «ОП»`.

**Открытый вопрос:** `1` или `01`, нужен ли текст «этаж».

---

## Что требует решения заказчика (сводка)

| № | Вопрос | Текущее поведение | Как менять |
|---|---|---|---|
| 1 | Исходные DWG | в репозиторий не кладутся (`.gitignore`), `input/` пуст | положить `7.2 ОП1.dwg` и `Марка этажа.dwg` в `input/` |
| 2 | Продукт/версия AutoCAD | ObjectDBX по `ACADVER`: 2013→19, 2015–2018→20–22; **LT не работает** | подтвердить полный AutoCAD и версию |
| 3 | п.4 «Свойства» | понято как свойства размера: `DIMTFILL=0`, текст H=250 | уточнить, если имелась в виду палитра свойств |
| 4 | Высота блока | 2400 при масштабе 1:1 | `*md:ins-scale*` / `*md:attr-height*` |
| 5 | Формат «Этаж» | `1`, `-1` — как в имени | доработка `md:floor-value` |
| 6 | Цвета п.6 | 1/5/2/4/3/200 | правка `*md:mark-colors*` |
| 7 | Листы и подпапки | оба флага `nil` | `*md:scan-paperspace*`, `*md:recurse*` |
| 8 | Объекты на выключенных слоях внутри блоков | обрабатываются | добавить фильтр в `md:do-obj` |

---

## Порядок приёмки (что делать по шагам)

### Шаг 1. Скачать рабочий файл

```powershell
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/moleval/MarshDWD/main/dist/MARSHDWG.lsp" -OutFile "$env:USERPROFILE\Downloads\MARSHDWG.lsp"
```

**Важно:** качать именно `raw.githubusercontent.com` (или Release / git-клон).
Ссылка на веб-страницу GitHub (`blob/...`) отдаёт файл перекодированным в UTF-8:
кириллица превращается в `Ěŕđęŕ ýňŕćŕ`, блок «Марка этажа» перестаёт находиться.
Признак правильного файла — 28 128 байт.

### Шаг 2. Загрузить в AutoCAD

```lisp
(load "C:/Users/molev/Downloads/MARSHDWG.lsp")
```

Ожидаемое приветствие: `MARSHDWG.lsp Ред. 1.2 загружен. Команды: …`

### Шаг 3. Указать источник блока

`MARSHDWGSRC` → выбрать `Марка этажа.dwg`.

### Шаг 4. Пилот на одном файле

`MARSHDWGFILE` → `7.2 ОП1.dwg`. Ожидаемый журнал:

```text
MARSHDWG Ред. 1.2 | источник блока: ...\Марка этажа.dwg
Файл: ...\7.2 ОП1.dwg

--- 7.2 ОП1
  [i] копия: ...\MARSHDWG_BACKUP\7.2 ОП1.dwg
  [OK] «Марка этажа» вставлен в 0,0, Этаж = 1
  [OK] сохранено
  слоёв выкл.: 9, серых: 4, марок осей: 93, размеров: …,
  текстов размеров: 39, изделий: 81, отметок: 3, высот: …,
  цветов: …, масок: …, штриховок: …, вставок: 1
```

### Шаг 5. Проверить глазами в AutoCAD

1. `СЛОЙ` — 10 слоёв выключены, 4 серых (251), заморозка не тронута.
2. Марка оси → `СВОЙСТВА` → цвет красный.
3. Текст размера → H = 250, «Фон: нет».
4. Текст изделия → H = 225, цвет по таблице п.6.
5. Штриховка → `СВОЙСТВА` → фон «Нет».
6. Блок в 0,0, атрибут «Этаж» = `1`.

### Шаг 6. Повторный прогон того же файла

Все счётчики должны быть нулями — подтверждение идемпотентности.

### Шаг 7. Пакетный прогон

`MARSHDWG` → выбрать папку. В журнале — `Обработано файлов: N из M`.

### Шаг 8. Откат, если что-то не так

Файлы лежат в `<папка>\MARSHDWG_BACKUP\` с исходными именами — скопировать
обратно.

---

## Изменённые файлы

| Файл | Что изменилось |
|---|---|
| `src/MARSHDWG.lsp` | 3 новых параметра, `md:on-p`, `md:scan-paperspace`, `md:collect`; идемпотентность в `md:set-h`/`md:set-color`/`md:bg-off`/`md:hatch-bg`/`md:do-text`/`md:do-grid`/`md:do-dim`/`md:do-layers`/`md:run-one`; `*md:rev*` = 1.1 |
| `dist/MARSHDWG.lsp` | пересобран: 27 335 б, 719 строк, sha256 `a60ac668…` |
| `tests/structure.py` | проверка «проглоченных defun» (глубина скобок по строкам) |
| `README.md` | п.4/п.6/п.12/п.13/п.14/листы/подпапки/ограничения/счётчики |
| `docs/VERIFICATION.md` | новые счётчики структуры, описание проверки скобок |
| `docs/REVIEW-RESPONSE.md` | новый файл: ответы на 14 пунктов + вопросы заказчику |
| `docs/HANDOFF.md` | версия 1.1, ссылка на REVIEW-RESPONSE |
| `MarshDWD-1.1.zip` | пересобран и проверен на чистой распаковке |

---

## Команды проверки (локально, без AutoCAD)

```bash
cd /home/user/Mark/dwg-auto
python3 tools/build.py          # пересборка dist из src
python3 tests/structure.py      # LISP-структура, скобки, зеркало правил
python3 tests/test_lisp_logic.py  # таблицы через настоящий код из src
```

Ожидаемо:

```text
OK   MARSHDWG.lsp (utf-8): top-level=90, defun=53, if=92, foreach=12, while=5, bytes=30476
OK   MARSHDWG.lsp (cp1251): top-level=90, defun=53, if=92, foreach=12, while=5, bytes=28128
OK   скобки: глубина 0, все 53 defun на верхнем уровне
OK   dist == src (CP1251/CRLF)
OK   функций md:*: 49, все вызываются
OK   команды: c:MARSHDWG, c:MARSHDWGCFG, c:MARSHDWGFILE, c:MARSHDWGSRC
OK   переменных *md:*: 34
OK   параметры *md:recurse*, *md:scan-paperspace*, *md:require-backup* используются
OK   правила LISP == tests/check_rules.py
ИТОГ: OK
```

---

## Статус записи в `moleval/MarshDWD`

Ред. 1.2 собрана **в самом `moleval/MarshDWD`** (ветка сессии, PR в `main`).
Разработка ведётся здесь; `moleval/Mark` больше не источник истины.

Ссылки:

* LISP: https://raw.githubusercontent.com/moleval/MarshDWD/main/dist/MARSHDWG.lsp
  (после мержа PR; в ветке — `arena/54cba4ea-marshdwd`)
* История правок 1.1 → 1.2: `docs/REVIEW-1.1.md`
