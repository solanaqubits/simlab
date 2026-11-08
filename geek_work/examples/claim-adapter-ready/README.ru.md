# Положительный контроль адаптера

Это **синтетическая редакторская фикстура**, отдельно от реальной записи шумной
орбиты. Источник заявляет гипотетический баланс `100 credits`; результат не
является доказательством ресурсного инварианта или экономической модели.
Нулевой commit в `source_snapshot` — явный тестовый маркер, не существующий Git-коммит.

Вручную подготовлены пять привязок во всех пяти логических ролях, прямая цитата
числа `100` и единицы `credits`, отметки чек-листа и пустой список вопросов.
`hypothesis` сохраняется. Математическое обязательство доказать сохранение на
трассах остаётся открытым и не блокирует редакторскую готовность.

`pins.json` документирует контрольные якоря. В эксплуатации их передаёт координатор
отдельно от кандидата; автоматическое доверие к соседнему pins-файлу не предполагается.
Оригинальный текст сохраняет emoji и CRLF без Unicode/строчной нормализации.

Из корня SimLab:

```sh
python3 -B geek_work/tools/geek_work_claim_adapter.py \
  --source-snapshot geek_work/examples/claim-adapter-ready/source.txt \
  --source-sha256 d26f1ffb801b4c2531a7afa1d61d5ceb073426db50ec018e5eaed146ae4483a2 \
  --expectations geek_work/examples/claim-adapter-ready/expectations.json \
  --expectations-sha256 d89b842e18302492a04804878c586f15cf0f0d0e7ce4786a0f3e0acda435f72b \
  --record geek_work/examples/claim-adapter-ready/record.json \
  --claim-map-bundle geek_work/examples/claim-adapter-ready/source-bundle \
  --claim-map-bundle-sha256 fd6ef4be66849d2c071b680a4cdd060999ec2b2c24b183e6bc41fdd0ce225057 \
  --source-claim-id synthetic-balance --source-revision 1 \
  --output /tmp/claim-adapter-new-package
```

Результат: код 0, `built`, `contract_preserved`. Файлы побайтово совпадают с
`expected-package/`, включая манифест. Повторный запуск в тот же каталог запрещён.

Для отрицательного контроля тесты используют неизменённый
[пример шумной орбиты](../claim-extraction-orbit/README.ru.md): код 1,
`build_blocked`, `extraction_not_record_consistent`, исходный `needs_context`.
При отказе план и кандидат не выдаются. Все четыре assurance-флага false.

[Полный контракт и ограничения](../../contracts/claim-adapter/README.md).

Локальный `.gitattributes` сохраняет CRLF только в трёх закреплённых копиях
исходника (`-text`, `whitespace=cr-at-eol`): байтовые хеши не должны меняться
из-за настройки Git. Общие проверки пробелов и остальная документация не изменены.
