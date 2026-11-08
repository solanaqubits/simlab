# Контроль валидатора редакторской записи: шумная орбита

Новый исполняемый пример построен из ручной записи
коммита e7b902f1 (`../../research/claim-extraction/FILLED-ORBIT-RECORD.json`; historical reference, not included in this public package).
Историческая запись, план Claim Transport и отчёты обоих пилотов не изменены.

Редакторская ведомость `expectations.json` фиксирует ранее выбранные восемь
привязок, область, статусы и открытый вопрос об основаниях единиц. Это вручную
заданный контрольный список, не результат автоматического поиска условий.
`pins.json` хранит воспроизводимые хеши; в эксплуатации ожидаемые хеши передаёт
координатор независимо от кандидата. Сам файл pins не удостоверяет полномочия.

При переносе в новый формат локатор снимка вынесен в `source_snapshot`, число
`1 / 4` получило собственный `literal_span`, а `unresolved_extraction_items`
отображено в `unresolved_questions`. Прежняя неподтверждённая аннотация единицы
сохранена как редакторское пояснение. `unknown` не превращён в `dimensionless`.

| Кандидат | Результат |
| --- | --- |
| `orbit-needs-context.json` | `needs_context`, 8 точных привязок, вопрос единиц открыт. |
| `orbit-invalid-promotion.json` | `invalid_input`: `mandatory_unresolved_question_incompatible_with_ready_for_transport`. |

Из корня SimLab, с новым выходным путём:

```sh
python3 -B geek_work/tools/geek_work_claim_extraction.py \
  --source-snapshot geek_work/examples/claim-transport-orbit/source-bundle/material-lean-source.txt \
  --source-sha256 c3a1b888897323fb7e761bb632a885bc08ff9366f14eaebaae79f301f8c296a3 \
  --expectations geek_work/examples/claim-extraction-orbit/expectations.json \
  --expectations-sha256 4f7374637b3c69fbfc46e44e69dbc6316c43454232e40ee780872956f4ad7e36 \
  --record geek_work/examples/claim-extraction-orbit/orbit-needs-context.json \
  --output /tmp/orbit-extraction-new-report.json
```

Ожидаемый код выхода — **1**: механическая проверка успешна, редакторский вопрос
остаётся открытым. Для отрицательного кандидата код — **2**. Сохранённые
`*.report.json` воспроизводятся побайтово тестами. Все четыре assurance-флага false.

Полный [контракт валидатора](../../contracts/claim-extraction/README.md).
Новый запуск Lean, автоизвлечение, адаптер в Transport, граф знаний и публикация
не входят в этот результат. Редакторские отметки не являются независимым аудитом.
