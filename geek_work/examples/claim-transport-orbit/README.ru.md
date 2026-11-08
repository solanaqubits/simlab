# Первый пилот Claim Transport: сходимость шумной орбиты

Готовый воспроизводимый пакет на реальном исходнике Leanbook. Это **проверка
переноса карточки со статусом `source_only`**, не новый запуск Lean и не повышение
статуса доказательств. Граф знаний и публичные репозитории не изменяются.

## Источник и контракт

Источник — `Verification/QuantumNoisyBBPSSWCritical.lean` из локального Git-коммита
`82124834f7aba30adcb460769d84f03eebfa5ce8`. Сигнатура
`QuantumNoisyBBPSSWCritical.subcriticalOrbit_tendsto_quarter` расположена на строках
239–241. Снимок всего файла сохранён без изменения байтов:
[material-lean-source.txt](source-bundle/material-lean-source.txt).
SHA-256: `c3a1b888897323fb7e761bb632a885bc08ff9366f14eaebaae79f301f8c296a3`.

Исходная выбранная цитата, без свободного пересказа:

```lean
theorem subcriticalOrbit_tendsto_quarter {γ F : ℝ}
    (hg : 0 ≤ γ) (hc : γ < criticalGamma) (h0 : 0 ≤ F) (h1 : F ≤ 1) :
    Tendsto (noisyOrbit γ F) atTop (nhds (1 / 4))
```

Четыре предпосылки представлены отдельными атомами; два ограничения на `F` также
помечены как область. Кванторный фрагмент — `{γ F : ℝ}`, а заключение — точное
выражение `Tendsto`. Число `1 / 4` хранится строкой с единицей `dimensionless`.
Распределение по ролям выполнено редакционно: полнота извлечения не доказана.

[План](plan.json) дополнительно сохраняет статус свидетельства, его привязку,
границы утверждения и открытые обязательства. Поэтому `contract_preserved`
относится ко всем выбранным проверяемым полям, а не только к набору предпосылок.

## Реально полученные исходы

| Вариант | Изменение | Результат |
|---|---|---|
| [preserved](candidates/preserved.json) | Все выбранные поля сохранены | `contract_preserved` |
| [without-noise-bound](candidates/without-noise-bound.json) | Удалены атом `γ < criticalGamma` и соответствующий фрагмент цитаты | `review_required` |
| [strict-upper-bound](candidates/strict-upper-bound.json) | `F ≤ 1` заменено на `F < 1`, с новым ID атома | `review_required` |
| [unaudited-proof-reference](candidates/unaudited-proof-reference.json) | `source_only` заменено на `formal_reported`, добавлено имя Lean-теоремы | `review_required` |
| [invalid-quote](candidates/invalid-quote.json) | Начало диапазона цитаты сдвинуто на один символ | `invalid_input` |

Отчёты: [сохранение](reports/preserved.json),
[удалённая предпосылка](reports/without-noise-bound.json),
[строгая граница](reports/strict-upper-bound.json),
[ссылка на доказательство](reports/unaudited-proof-reference.json),
[повреждённая цитата](reports/invalid-quote.json).

`review_required` не означает «ложно». В частности, сужение области с `F ≤ 1` до
`F < 1` может быть корректным логическим следствием; режим `exact_contract` требует
сохранения самого контракта и не доказывает такие переходы. Удаление условия на
шум также обнаруживается структурно, без поиска математического контрпримера.

Во всех пяти отчётах остаются `false`: `semantic_equivalence_verified`,
`source_extraction_complete`, `kernel_replayed`, `publication_authorized`.

## Воспроизведение

Из корня частного SimLab, без сети и без установленного Lean:

```sh
python3 geek_work/examples/claim-transport-orbit/replay.py \
  --manifest-sha256 2460bed9bc5d2c4c98fdee47058d9e737b8dc61c20cb75f848946440ef666951
```

Команда проверяет все 17 закреплённых файлов данных и побайтово воспроизводит
пять отчётов. [Манифест](manifest.json) фиксирует конкретный исходник, план,
кандидаты и отчёты. Его хеш — внешний якорь этой квитанции, а не выбор кандидата.
Это не криптографическая аутентификация координатора или удалённого репозитория.

Один случай можно проверить штатным CLI, указав новый путь результата:

```sh
python3 geek_work/tools/geek_work_claim_transport.py check \
  --bundle geek_work/examples/claim-transport-orbit/source-bundle \
  --source-sha256 022bbbc4659daa6cb249aed9bdb8dc8a90c85f7fb9bd828ab53964458398281b \
  --plan geek_work/examples/claim-transport-orbit/plan.json \
  --plan-sha256 ede1850f2cc6adc8f35aad4d67056450dadbe13f485b56163439502c704a89ea \
  --candidate geek_work/examples/claim-transport-orbit/candidates/preserved.json \
  --output /tmp/claim-transport-orbit-preserved.json
```

Существующий файл результата не перезаписывается. Исторические заявления об
аудите исходного квантового модуля не включены как свежие свидетельства пилота.
Математические исходники не изменялись и не компилировались повторно.
