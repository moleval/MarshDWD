;;; ============================================================================
;;; MARSHDWG.lsp — автообработка DWG: слои, цвета, высоты текста и вставка
;;; блока «Марка этажа» с атрибутом «Этаж».
;;;
;;; Запуск:  (load "D:/MARSHDWG.lsp")
;;; Команды: MARSHDWG      — пакетный прогон по папке
;;;          MARSHDWGFILE  — прогон по одному файлу (обкатка)
;;;          MARSHDWGSRC   — указать DWG-источник блока «Марка этажа»
;;;          MARSHDWGCFG   — напечатать действующие правила
;;;
;;; Файл: CP1251 + CRLF. Правки — точечные.
;;; Работа идёт через ActiveX/ObjectDBX: файлы не открываются в редакторе,
;;; окна не появляются, поэтому возможен пакетный прогон.
;;;
;;; Ред. 1.2 — после ревью: backup-подпапка вне обхода, фон штриховки не
;;; считается изменением, require-backup работает, счётчики идемпотентны.
;;; ============================================================================

(vl-load-com)

(setq *md:rev* "Ред. 1.2")

;;; ---------------------------------------------------------------------------
;;; 1. ПРАВИЛА (единственное место, где что-то настраивается)
;;; ---------------------------------------------------------------------------

(setq *md:block-name* "Марка этажа")      ; имя блока-марки
(setq *md:block-file* "")                 ; DWG-источник блока; "" = спросить
(setq *md:block-layer* "0")               ; слой вставки
(setq *md:attr-tag* "Этаж")               ; тег атрибута
(setq *md:ins-pt* (list 0.0 0.0 0.0))     ; точка вставки (X Y Z)
(setq *md:ins-scale* 1.0)                 ; масштаб вставки (1:1)
(setq *md:ins-rot* 0.0)                   ; поворот, рад
(setq *md:skip-if-exists* t)              ; не вставлять повторно
(setq *md:attr-height* nil)               ; nil = не менять высоту атрибута
(setq *md:name-marker* "ОП")              ; маркер второй части имени файла
(setq *md:backup-subdir* "MARSHDWG_BACKUP") ; подпапка резервных копий
(setq *md:require-backup* t)              ; t = без копии файл не обрабатывается
(setq *md:scan-paperspace* nil)           ; t = обрабатывать и листы (Layout)
(setq *md:recurse* nil)                   ; t = обходить вложенные папки
(setq *md:log-name* "MARSHDWG_LOG.txt")     ; журнал прогона

;; п.1 Выключить слои
(setq *md:off-layers*
  (list "A-ANNO-NOTE"
        "A-AREA-IDEN"
        "A-DETL"
        "A-FLOR-IDEN"
        "G-ANNO-NOTE"
        "G-ANNO-REVC"
        "G-ANNO-REVC-IDEN"
        "G-ANNO-TEXT"
        "I-FURN"
        "P-SANR-FIXT"))

;; п.2 Серый цвет 251
(setq *md:gray-color* 251)
(setq *md:gray-layers*
  (list "A-ANNO-DIMS"
        "A-ANNO-DIMS-100"
        "S-GRID"
        "S-GRID-IDEN"))

;; п.3 Марки осей — красный (объекты слоя, включая содержимое блоков)
(setq *md:grid-layer* "S-GRID-IDEN")
(setq *md:grid-color* 1)

;; п.4 Размеры: высота текста 250, задний план — нет
(setq *md:dim-height* 250.0)
(setq *md:dim-layers*
  (list "A-ANNO-DIMS" "A-ANNO-DIMS-100" "G-ANNO-DIMS"))
(setq *md:dim-tfill* 0)                   ; DIMTFILL стиля размера: 0 = нет фона

;; п.5 Обозначения изделий — высота 225
(setq *md:prod-height* 225.0)
(setq *md:prod-layers*
  (list "A-DOOR-IDEN" "A-GLAZ-IDEN" "A-WALL-IDEN"))

;; п.6 Марки изделий и отметки: цвет, задний план не скрывать.
;; Шаблоны wcmatch, порядок важен: EI проверяется первым.
(setq *md:mark-colors*
  (list (cons "*EI*" 1)     ; EI — красный
        (cons "Д*"   5)     ; двери (ДВ, ДГ, ДС, ДСВ, ДН, ДПВ) — синий
        (cons "ОК*"  2)     ; окна — жёлтый
        (cons "ББ*"  2)     ; балконные блоки — жёлтый
        (cons "Б*"   2)     ; балконы — жёлтый
        (cons "ОЛ*"  4)     ; лоджии — голубой
        (cons "ВТ*"  3)))   ; витражи — зелёный

;; п.6.0 Символ не подошёл ни под один шаблон — цвет по слою.
(setq *md:prod-default*
  (list (cons "A-GLAZ-IDEN" 2)   ; окна/балконы
        (cons "A-DOOR-IDEN" 5)   ; двери
        (cons "A-WALL-IDEN" 3))) ; витражи

;; п.6.1 Отметки — фиолетовый
(setq *md:elev-layers* (list "G-ANNO-DIMS"))
(setq *md:elev-color* 200)

;; п.7 Штриховки: цвет фона «Нет»
(setq *md:hatch-bg-off* t)

;;; ---------------------------------------------------------------------------
;;; 2. СЛУЖЕБНОЕ
;;; ---------------------------------------------------------------------------

(setq *md:logfile* nil)
(setq *md:st* nil)
(setq *md:dbx* nil)

(defun md:str (x)
  (cond ((null x) "")
        ((= (type x) 'STR) x)
        (t (vl-princ-to-string x))))

(defun md:trim (s / a b)
  (setq s (md:str s))
  (setq a 1 b (strlen s))
  (while (and (<= a b) (= " " (substr s a 1))) (setq a (1+ a)))
  (while (and (>= b a) (= " " (substr s b 1))) (setq b (1- b)))
  (if (> a b) "" (substr s a (1+ (- b a)))))

(defun md:wlog (m / f)
  (if *md:logfile*
    (progn
      (setq f (vl-catch-all-apply 'open (list *md:logfile* "a")))
      (if (not (vl-catch-all-error-p f))
        (progn
          (vl-catch-all-apply 'write-line (list (md:str m) f))
          (vl-catch-all-apply 'close (list f))))))
  (princ))

(defun md:log-reset (path / f)
  (setq *md:logfile* path)
  (if path
    (progn
      (setq f (vl-catch-all-apply 'open (list path "w")))
      (if (not (vl-catch-all-error-p f))
        (progn
          (vl-catch-all-apply 'write-line
            (list (strcat "=== MARSHDWG.lsp " *md:rev* " ===") f))
          (vl-catch-all-apply 'close (list f))))))
  path)

(defun md:emit (m)
  (setq m (md:str m))
  (princ (strcat "\n" m))
  (md:wlog m)
  (princ))

(defun md:warn (m)
  (md:emit (strcat "  [ВНИМАНИЕ] " (md:str m))))

(defun md:try (fn obj arg / r)
  (setq r (if arg
            (vl-catch-all-apply fn (list obj arg))
            (vl-catch-all-apply fn (list obj))))
  (if (vl-catch-all-error-p r) nil r))

(defun md:try-set (fn obj val / r)
  (setq r (vl-catch-all-apply fn (list obj val)))
  (if (vl-catch-all-error-p r) nil t))

(defun md:bump (k n / cell)
  (setq n (if n n 1))
  (if (setq cell (assoc k *md:st*))
    (setq *md:st* (subst (cons k (+ (cdr cell) n)) cell *md:st*))
    (setq *md:st* (append *md:st* (list (cons k n)))))
  (cdr (assoc k *md:st*)))

(defun md:stat (k / cell)
  (if (setq cell (assoc k *md:st*)) (cdr cell) 0))

(defun md:objname (o / n)
  (setq n (md:try 'vla-get-ObjectName o nil))
  (if n (strcase n) ""))

(defun md:layer-of (o / l)
  (setq l (md:try 'vla-get-Layer o nil))
  (if l (strcase l) ""))

(defun md:in-list (s lst / u r)
  (setq u (strcase (md:str s)) r nil)
  (foreach x lst
    (if (= u (strcase x)) (setq r t)))
  r)

(defun md:item (coll name / r)
  (if coll
    (progn
      (setq r (vl-catch-all-apply 'vla-Item (list coll name)))
      (if (vl-catch-all-error-p r) nil r))))

(defun md:objlist (v / r)
  (cond ((null v) nil)
        ((= (type v) 'VARIANT)
         (setq r (vlax-variant-value v))
         (if (vlax-safearrayp r) (vlax-safearray->list r) nil))
        ((vlax-safearrayp v) (vlax-safearray->list v))
        (t nil)))

;; Текст MTEXT без форматирования: срезаем управляющие группы.
(defun md:plain (s / i j c out n)
  (setq s (md:str s) out "" i 1 n (strlen s))
  (while (<= i n)
    (setq c (substr s i 1))
    (cond
      ((= c "\\")
       (setq j (vl-string-search ";" s (1- (+ i 2))))
       (if j (setq i (+ j 2)) (setq i (+ i 2))))
      ((or (= c "{") (= c "}")) (setq i (1+ i)))
      (t (setq out (strcat out c)) (setq i (1+ i)))))
  (setq out (vl-string-translate "\\" " " out))
  (md:trim out))

;;; ---------------------------------------------------------------------------
;;; 3. ИЗМЕНЕНИЯ ОБЪЕКТОВ
;;; ---------------------------------------------------------------------------

(defun md:set-h (o h / cur done)
  (if (and (vlax-property-available-p o 'Height t)
           (not (equal (setq cur (md:try 'vla-get-Height o nil)) h 1e-6)))
    (progn
      (setq done (md:try-set 'vla-put-Height o h))
      (if done (md:bump "height") (md:bump "locked"))
      done)))

(defun md:set-color (o c / cur done)
  (if (not (equal (setq cur (md:try 'vla-get-Color o nil)) c))
    (progn
      (setq done (md:try-set 'vla-put-Color o c))
      (if done (md:bump "color") (md:bump "locked"))
      done)))

;; Задний план текста «нет» = BackgroundFill в положение «как у чертежа»
;; (:vlax-false), а не «маска» (:vlax-true).
;; «Включено» для :vlax-true / 1 / -1, «выключено» для nil / 0 / :vlax-false.
;; Разные версии AutoCAD отдают то -1, то 1 — сравнивать через eq нельзя.
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

;; Штриховка: цвет фона «Нет» (EntityColor с методом None).
(defun md:hatch-bg (o / c m)
  (if *md:hatch-bg-off*
    (progn
      (setq c (md:try 'vla-get-BackgroundColor o nil))
      (if c (setq m (md:try 'vla-get-ColorMethod c nil)))
      ;; Фон уже «Нет» (ColorMethod = 0) или BackgroundColor недоступен:
      ;; менять нечего, счётчик не растёт (иначе идемпотентность ломается).
      (if (or (null c) (and (numberp m) (= m 0)))
        nil
        (progn
          (md:try-set 'vla-put-EntityColor c -939524096)
          (md:try-set 'vla-put-ColorMethod c 0)
          (md:try-set 'vla-put-BackgroundColor o c)
          (if (= 0 (md:try 'vla-get-ColorMethod c nil))
            (md:bump "hatch")))))))

(defun md:text-p (nm)
  (or (= nm "ACDBMTEXT")
      (= nm "ACDBTEXT")
      (= nm "ACDBATTRIB")
      (= nm "ACDBATTRIBUTEDEFINITION")))

(defun md:mark-color (txt / u r pair)
  (setq u (strcase (md:plain txt)) r nil)
  (foreach pair *md:mark-colors*
    (if (and (not r) (wcmatch u (car pair))) (setq r (cdr pair))))
  r)

(defun md:layer-default (lay / pair res)
  (foreach pair *md:prod-default*
    (if (and (not res) (md:in-list lay (list (car pair)))) (setq res (cdr pair))))
  res)

;; Тексты: отметки, размеры, обозначения изделий.
(defun md:do-text (o / lay txt col chg)
  (setq lay (md:layer-of o))
  (cond
    ((md:in-list lay *md:elev-layers*)
     (setq chg nil)
     (if (md:set-h o *md:dim-height*) (setq chg t))
     (if (md:bg-off o) (setq chg t))
     (if (md:set-color o *md:elev-color*) (setq chg t))
     (if chg (md:bump "elev")))
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
     (if chg (md:bump "prod")))))

;; Марки осей: цвет красный у всех объектов слоя (в т.ч. внутри блоков).
(defun md:do-grid (o)
  (if (md:set-color o *md:grid-color*) (md:bump "grid")))

;; Размеры: фон «нет» в стиле, высота текста через свойство, если доступно.
(defun md:do-dim (o / style ds tf)
  (setq style (md:try 'vla-get-StyleName o nil))
  (if style
    (progn
      (setq ds (md:item (md:try 'vla-get-DimStyles
                          (if *md:dbx* *md:dbx* (md:try 'vla-get-ActiveDocument
                                                        (vlax-get-acad-object) nil))
                          nil)
                        style))
      (cond
        ((null ds) (md:warn (strcat "стиль размера не найден: " style)))
        (t
         (setq tf (md:try 'vla-get-Dimtfill ds nil))
         (if (and (numberp tf) (/= tf *md:dim-tfill*))
           (progn
             (md:try-set 'vla-put-Dimtfill ds *md:dim-tfill*)
             (md:bump "dim"))))))
    (md:warn "у размера нет стиля — DIMTFILL не проверен"))
  (if (md:set-h o *md:dim-height*) (md:bump "dim-text")))

(defun md:do-obj (o / nm lay)
  (setq nm (md:objname o))
  (setq lay (md:layer-of o))
  (cond
    ((= nm "ACDBHATCH") (md:hatch-bg o))
    ((wcmatch nm "*DIMENSION*") (md:do-dim o))
    ((md:in-list lay (list *md:grid-layer*)) (md:do-grid o))
    ((and (md:in-list lay *md:elev-layers*) (not (md:text-p nm)))
     (if (md:set-color o *md:elev-color*) (md:bump "elev")))
    ((md:text-p nm) (md:do-text o))
    (t nil)))

(defun md:scan-space (space)
  (if space (vlax-for o space (md:do-obj o))))

;; Листы (Layout): только пространство листа, Model — уже обработан.
;; TabOrder > 0 отсекает модель; если свойство недоступно, обходим все Layouts.
(defun md:scan-paperspace (dbx / lays lay ps tno nm)
  (setq lays (md:try 'vla-get-Layouts dbx nil))
  (if lays
    (vlax-for lay lays
      (setq nm (md:try 'vla-get-Name lay nil))
      (setq tno (md:try 'vla-get-TabOrder lay nil))
      ;; Модель уже обошли через ModelSpace: отсекаем по имени и TabOrder.
      (if (and (not (and nm (= (strcase nm) "MODEL")))
               (or (not (numberp tno)) (> tno 0)))
        (progn
          (setq ps (md:try 'vla-get-Block lay nil))
          (if ps (md:scan-space ps)))))))

(defun md:scan-blocks (dbx / blocks b)
  (setq blocks (md:try 'vla-get-Blocks dbx nil))
  (if blocks
    (vlax-for b blocks
      (if (and (not (eq :vlax-true (md:try 'vla-get-IsLayout b nil)))
               (not (eq :vlax-true (md:try 'vla-get-IsXRef b nil))))
        (vlax-for o b (md:do-obj o))))))

;;; ---------------------------------------------------------------------------
;;; 4. СЛОИ
;;; ---------------------------------------------------------------------------

(defun md:do-layers (dbx / lays name lay cur)
  (setq lays (md:try 'vla-get-Layers dbx nil))
  (cond
    ((null lays) (md:warn "коллекция слоёв недоступна"))
    (t
     (foreach name *md:off-layers*
       (setq lay (md:item lays name))
       (cond
         ((null lay) (md:warn (strcat "слой не найден: " name)))
         ((md:on-p (md:try 'vla-get-LayerOn lay nil))
          (if (md:try-set 'vla-put-LayerOn lay :vlax-false)
            (md:bump "layers-off")))))
     (foreach name *md:gray-layers*
       (setq lay (md:item lays name))
       (cond
         ((null lay) (md:warn (strcat "слой не найден: " name)))
         (t
          (setq cur (md:try 'vla-get-Color lay nil))
          (if (and (numberp cur) (/= cur *md:gray-color*))
            (if (md:try-set 'vla-put-Color lay *md:gray-color*)
              (md:bump "layers-gray")))))))))

;;; ---------------------------------------------------------------------------
;;; 5. ObjectDBX
;;; ---------------------------------------------------------------------------

(defun md:progids (/ n lst)
  (setq n (atoi (getvar "ACADVER")))
  (if (< n 16) (setq n 32))
  (setq lst nil)
  (while (>= n 16)
    (setq lst (append lst (list (strcat "ObjectDBX.AxDbDocument." (itoa n)))))
    (setq n (1- n)))
  lst)

(defun md:dbx-new (/ ids dbx id)
  (setq ids (md:progids))
  (foreach id ids
    (if (null dbx)
      (progn
        (setq dbx (vl-catch-all-apply 'vla-getinterfaceobject
                    (list (vlax-get-acad-object) id)))
        (if (vl-catch-all-error-p dbx) (setq dbx nil)))))
  dbx)

(defun md:dbx-open (path / dbx)
  (setq dbx (md:dbx-new))
  (cond
    ((null dbx) (md:warn "ObjectDBX недоступен") nil)
    (t
     (if (vl-catch-all-error-p
           (vl-catch-all-apply 'vla-open (list dbx path)))
       (progn (md:warn (strcat "не открыт: " path)) (setq dbx nil)))
     dbx)))

(defun md:dbx-save (dbx path / r)
  (setq r (vl-catch-all-apply 'vla-SaveAs (list dbx path)))
  (if (vl-catch-all-error-p r)
    (progn
      (setq r (vl-catch-all-apply 'vlax-invoke-method (list dbx 'SaveAs path)))
      (not (vl-catch-all-error-p r)))
    t))

;;; ---------------------------------------------------------------------------
;;; 6. ВСТАВКА БЛОКА «МАРКА ЭТАЖА»
;;; ---------------------------------------------------------------------------

(defun md:last-search (s pat / pos next from)
  (setq from 1 pos nil next t)
  (while next
    (setq next (vl-string-search pat s (1- from)))
    (if next
      (progn (setq pos (1+ next)) (setq from (+ pos (strlen pat))))))
  pos)

(defun md:alnum-p (c)
  (wcmatch c "[A-Z0-9А-Я]*"))

;; Вторая часть имени файла после последнего «ОП»; nil — если перед «ОП» стоит
;; буква/цифра (ПОП1) или после «ОП» пусто.
(defun md:floor-value (path / name u i m v)
  (setq name (vl-filename-base path))
  (setq u (strcase name))
  (setq m (strcase *md:name-marker*))
  (setq i (md:last-search u m))
  (setq v nil)
  (if i
    (progn
      (setq v (md:trim (substr name (+ i (strlen m)))))
      (if (or (= v "")
              (and (> i 1) (md:alnum-p (substr u (1- i) 1))))
        (setq v nil))))
  v)

(defun md:has-insert (dbx / msp found nm pt)
  (setq msp (md:try 'vla-get-ModelSpace dbx nil))
  (if msp
    (vlax-for o msp
      (if (= (md:objname o) "ACDBBLOCKREFERENCE")
        (progn
          (setq nm (md:try 'vla-get-Name o nil))
          (if (and nm (= (strcase nm) (strcase *md:block-name*)))
            (progn
              (setq pt (md:try 'vla-get-InsertionPoint o nil))
              (if (and pt
                       (equal (vlax-safearray->list (vlax-variant-value pt))
                              *md:ins-pt* 1e-4))
                (setq found t))))))))
  found)

(defun md:copy-block (src dst bname / blk arr r)
  (setq blk (md:item (md:try 'vla-get-Blocks src nil) bname))
  (cond
    ((null blk) (md:warn (strcat "в источнике нет блока: " bname)) nil)
    (t
     (setq arr (vlax-make-safearray vlax-vbObject '(0 . 0)))
     (vlax-safearray-put-element arr 0 blk)
     (setq r (vl-catch-all-apply 'vla-CopyObjects
               (list src arr (md:try 'vla-get-Blocks dst nil))))
     (if (vl-catch-all-error-p r)
       (progn (md:warn (strcat "копирование блока: "
                               (vl-catch-all-error-message r)))
              nil)
       (progn (md:bump "block-def") t)))))

(defun md:fill-attrs (ref val / atts att tag done)
  (setq atts (md:objlist (md:try 'vla-get-Attributes ref nil)))
  (foreach att atts
    (setq tag (md:try 'vla-get-TagString att nil))
    (if (and tag (= (strcase tag) (strcase *md:attr-tag*)))
      (progn
        (md:try-set 'vla-put-TextString att val)
        (if *md:attr-height*
          (md:try-set 'vla-put-Height att *md:attr-height*))
        (setq done t))))
  done)

(defun md:insert-mark (tgt src path / val msp ref)
  (setq val (md:floor-value path))
  (cond
    ((null val)
     (md:emit "  [ПРОПУСК] в имени файла нет «ОП» — блок не вставляется")
     (md:bump "skip-no-marker"))
    ((and *md:skip-if-exists* (md:has-insert tgt))
     (md:emit "  [ПРОПУСК] блок уже вставлен в 0,0")
     (md:bump "skip-inserted"))
    (t
     (if (null (md:item (md:try 'vla-get-Blocks tgt nil) *md:block-name*))
       (md:copy-block src tgt *md:block-name*))
     (setq msp (md:try 'vla-get-ModelSpace tgt nil))
     (setq ref (vl-catch-all-apply 'vla-InsertBlock
                 (list msp (vlax-3d-point *md:ins-pt*) *md:block-name*
                       *md:ins-scale* *md:ins-scale* *md:ins-scale* *md:ins-rot*)))
     (cond
       ((vl-catch-all-error-p ref)
        (md:warn (strcat "вставка блока: " (vl-catch-all-error-message ref))))
       (t
        (md:try-set 'vla-put-Layer ref *md:block-layer*)
        (md:bump "insert")
        (if (md:fill-attrs ref val)
          (md:emit (strcat "  [OK] «" *md:block-name* "» вставлен в 0,0, "
                           *md:attr-tag* " = " val))
          (md:warn (strcat "у блока нет атрибута «" *md:attr-tag* "»"))))))))

;;; ---------------------------------------------------------------------------
;;; 7. ОБРАБОТКА ОДНОГО ФАЙЛА
;;; ---------------------------------------------------------------------------

(defun md:backup (path / dir dst r)
  (setq dir (strcat (vl-filename-directory path) "/" *md:backup-subdir*))
  (if (not (vl-file-directory-p dir))
    (vl-catch-all-apply 'vl-mkdir (list dir)))
  (setq dst (strcat dir "/" (vl-filename-base path) ".dwg"))
  (if (findfile dst)
    (progn (md:emit (strcat "  [i] копия уже есть: " dst)) t)
    (progn
      (setq r (vl-catch-all-apply 'vl-file-copy (list path dst)))
      (if (vl-catch-all-error-p r)
        (progn (md:warn "резервная копия не сделана") nil)
        (progn (md:emit (strcat "  [i] копия: " dst)) t)))))

(defun md:run-one (path srcpath / tgt src ok)
  (md:emit (strcat "\n--- " (vl-filename-base path)))
  (setq *md:st* nil)
  (setq ok t)
  (if (not (md:backup path))
    (if *md:require-backup*
      (progn (md:warn "файл пропущен: нет резервной копии") (setq ok nil))
      (md:warn "продолжаю без резервной копии")))
  (if ok
    (progn
      (setq tgt (md:dbx-open path))
      (setq src (md:dbx-open srcpath))
      (setq *md:dbx* tgt)))
  (cond
    ((not ok) nil)
    ((or (null tgt) (null src))
     (md:warn "файл не открыт — пропуск")
     (setq ok nil))
    (t
     (md:do-layers tgt)
     (md:scan-space (md:try 'vla-get-ModelSpace tgt nil))
     (if *md:scan-paperspace* (md:scan-paperspace tgt))
     (md:scan-blocks tgt)
     (md:insert-mark tgt src path)
     (if (md:dbx-save tgt path)
       (md:emit "  [OK] сохранено")
       (progn (md:warn "не сохранено") (setq ok nil)))))
  (setq *md:dbx* nil)
  (if tgt (vl-catch-all-apply 'vlax-release-object (list tgt)))
  (if src (vl-catch-all-apply 'vlax-release-object (list src)))
  (if (> (md:stat "locked") 0)
    (md:warn (strcat "не изменено объектов на заблокированных слоях: "
                     (itoa (md:stat "locked"))
                     " — снимите блокировку слоёв и повторите")))
  (md:emit (strcat "  слоёв выкл.: " (itoa (md:stat "layers-off"))
                   ", серых: " (itoa (md:stat "layers-gray"))
                   ", марок осей: " (itoa (md:stat "grid"))
                   ", стилей размеров: " (itoa (md:stat "dim"))
                   ", текстов размеров: " (itoa (md:stat "dim-text"))
                   ", изделий: " (itoa (md:stat "prod"))
                   ", отметок: " (itoa (md:stat "elev"))
                   ", высот: " (itoa (md:stat "height"))
                   ", цветов: " (itoa (md:stat "color"))
                   ", масок: " (itoa (md:stat "bg-off"))
                   ", штриховок: " (itoa (md:stat "hatch"))
                   ", вставок: " (itoa (md:stat "insert"))))
  ok)

;;; ---------------------------------------------------------------------------
;;; 8. КОМАНДЫ
;;; ---------------------------------------------------------------------------

(defun md:src-path (/ p)
  (cond
    ((and *md:block-file* (/= *md:block-file* "") (findfile *md:block-file*))
     *md:block-file*)
    (t
     (setq p (getfiled "DWG с блоком «Марка этажа»" "" "dwg" 0))
     (if p (setq *md:block-file* p))
     p)))

(defun md:pick-folder (/ sh res path self)
  (setq sh (vl-catch-all-apply 'vla-getinterfaceobject
             (list (vlax-get-acad-object) "Shell.Application")))
  (if (vl-catch-all-error-p sh) (setq sh nil))
  (if sh
    (progn
      (setq res (vl-catch-all-apply 'vlax-invoke-method
                  (list sh 'BrowseForFolder 0 "Папка с DWG для обработки" 0)))
      (if (not (vl-catch-all-error-p res))
        (progn
          (setq self (md:try 'vla-get-Self res nil))
          (if self (setq path (md:try 'vla-get-Path self nil)))))
      (vl-catch-all-apply 'vlax-release-object (list sh))
      path)
    (getstring t "\nПапка с DWG: ")))

(defun c:MARSHDWGFILE (/ f src log)
  (setq f (getfiled "DWG для обработки" "" "dwg" 0))
  (cond
    ((null f) (princ "\nОтменено."))
    (t
     (setq src (md:src-path))
     (cond
       ((or (null src) (not (findfile src)))
        (princ "\nНе указан DWG с блоком «Марка этажа» (MARSHDWGSRC)."))
       (t
        (setq log (strcat (vl-filename-directory f) "/" *md:log-name*))
        (md:log-reset log)
        (md:emit (strcat "MARSHDWG " *md:rev* " | источник блока: " src))
        (md:emit (strcat "Файл: " f))
        (md:run-one f src)
        (md:emit (strcat "\nЖурнал: " log))))))
  (princ))

;; Список DWG в папке; при *md:recurse* — и во вложенных папках.
(defun md:collect (folder / files name sub res)
  (setq files (vl-directory-files folder "*.dwg" 1))
  (setq res nil)
  (foreach name files
    (setq res (append res (list (strcat folder "/" name)))))
  (if *md:recurse*
    (foreach sub (vl-directory-files folder "*.*" -1)
      ;; MARSHDWG_BACKUP в обход не берём: там исходники для отката.
      (if (and (not (member sub (list "." "..")))
               (/= (strcase sub) (strcase *md:backup-subdir*))
               (vl-file-directory-p (strcat folder "/" sub)))
        (setq res (append res (md:collect (strcat folder "/" sub)))))))
  res)

(defun c:MARSHDWG (/ folder files k src log path)
  (setq folder (md:pick-folder))
  (cond
    ((or (null folder) (= folder "")) (princ "\nОтменено."))
    (t
     (setq folder (vl-string-right-trim "\\/" folder))
     (setq src (md:src-path))
     (cond
       ((or (null src) (not (findfile src)))
        (princ "\nНе указан DWG с блоком «Марка этажа» (MARSHDWGSRC)."))
       (t
        (setq files (md:collect folder))
        (setq log (strcat folder "/" *md:log-name*))
        (md:log-reset log)
        (md:emit (strcat "MARSHDWG " *md:rev* " | источник блока: " src))
        (md:emit (strcat "Папка: " folder " | файлов: " (itoa (length files))))
        (setq k 0)
        (foreach path files
          (if (md:run-one path src) (setq k (1+ k))))
        (md:emit (strcat "\nОбработано файлов: " (itoa k)
                         " из " (itoa (length files))))
        (md:emit (strcat "Журнал: " log))))))
  (princ))

(defun c:MARSHDWGSRC (/ p)
  (setq p (getfiled "DWG с блоком «Марка этажа»" "" "dwg" 0))
  (if p
    (progn (setq *md:block-file* p)
           (md:emit (strcat "Источник блока: " p))))
  (princ))

(defun md:print-list (caption lst)
  (md:emit (strcat caption " (" (itoa (length lst)) "):"))
  (foreach x lst (md:emit (strcat "   - " (md:str x)))))

(defun c:MARSHDWGCFG (/ pair)
  (md:emit (strcat "MARSHDWG " *md:rev* " — правила"))
  (md:print-list "1. Слои выключить" *md:off-layers*)
  (md:print-list (strcat "2. Слои, цвет " (itoa *md:gray-color*)) *md:gray-layers*)
  (md:emit (strcat "3. Марки осей: слой " *md:grid-layer* ", цвет "
                   (itoa *md:grid-color*)))
  (md:emit (strcat "4. Размеры: H=" (rtos *md:dim-height* 2 0)
                   ", DIMTFILL=" (itoa *md:dim-tfill*)))
  (md:print-list "   слои размеров" *md:dim-layers*)
  (md:emit (strcat "5. Обозначения изделий: H=" (rtos *md:prod-height* 2 0)))
  (md:print-list "   слои изделий" *md:prod-layers*)
  (md:emit "6. Марки изделий: цвет")
  (foreach pair *md:mark-colors*
    (md:emit (strcat "   " (car pair) " -> " (itoa (cdr pair)))))
  (md:print-list (strcat "6.1 Отметки, цвет " (itoa *md:elev-color*))
                 *md:elev-layers*)
  (md:emit (strcat "7. Штриховки: фон "
                   (if *md:hatch-bg-off* "нет" "не менять")))
  (md:emit (strcat "Блок: «" *md:block-name* "», атрибут «" *md:attr-tag*
                   "», точка " (vl-princ-to-string *md:ins-pt*)
                   ", масштаб " (rtos *md:ins-scale* 2 3)))
  (md:emit (strcat "Файлы с «" *md:name-marker*
                   "» в имени: атрибут = часть после «"
                   *md:name-marker* "»; без маркера — блок не вставляется"))
  (princ))

(princ (strcat "\nMARSHDWG.lsp " *md:rev*
               " загружен. Команды: MARSHDWG (папка), MARSHDWGFILE (файл), "
               "MARSHDWGSRC (источник блока), MARSHDWGCFG (правила)."))
(princ)
