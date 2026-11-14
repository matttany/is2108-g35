# C03: demand forecasts and price quotes

## Run locally

From the repository root, activate your virtual environment and run:

```powershell
python -m pip install -r requirements.txt
cd Delaundry
python manage.py migrate
python manage.py runserver
```

Log in as a customer with a residence, then visit http://127.0.0.1:8000/storefront/availability/.
The table shows estimates; **Review price quote** recalculates the final price on the server and saves it.
The resulting `/storefront/quotes/<id>/` page shows the saved amount and expiry.
Only the customer who created the quote can view it.
This does not submit an order, charge money or reserve machines.

The committed model can be used immediately. To reproduce the synthetic CSV and model, run from `Delaundry`:

```powershell
python -m ml.generate_training_data
python -m ml.train_model
```

Neither command writes to the application database. Restart the server after changing calendar files.
Use the pinned ML dependencies when loading the saved model. Version 1.7.2 supports both Python 3.12 and 3.14;
it was used because Windows Application Control blocked a compiled module in 1.9.1 on the development machine.
Only load joblib files produced by this project: joblib deserialisation must not be used for user uploads.

## Features and their sources

Each row predicts the number of **new requests between the forecast time and pickup start**, for one hall/window.
Existing bookings are an input, not part of this target.

| Feature | Live source |
| --- | --- |
| residence | CustomerProfile.residence.name; never a customer-supplied hall parameter |
| weekday | Pickup date in Singapore time; Monday = 0 |
| pickup_hour | Start of the two-hour service window, 08:00 through 20:00 |
| is_term_time | Local academic_calendar.csv |
| is_public_holiday | Local public_holidays.csv |
| lead_hours | Hours between the current time and pickup start |
| recent_requests | LaundryOrder submissions for the hall in the preceding 24 hours, including later cancellations |
| known_bookings | Reserved washers in that hall/date/window; dryers are not counted a second time |
| operational_machines | ACTIVE washers and dryers in active rooms of the active hall |

No name, email, unit number or user ID enters the model. The quote separately stores the customer and address for ownership and later order submission.
Until C04 creates actual LaundryOrder records, recent_requests correctly stays zero. Quote views and quote creation do not count as requests.

Calendar coverage is **1 January–31 December 2026**, including observed public holidays. Dates outside that range use neutral pricing until both CSVs are extended.
For this regular-undergraduate prototype, term includes teaching, recess, reading, examinations and orientation week. Special term is classified as vacation.
Public holidays are separate from term/vacation, so both flags can be 1. NUS Well-Being Days are not national public holidays and are not included in that flag.

Sources: [NUS AY2025/2026](https://www.nus.edu.sg/registrar/docs/default-source/calendar/ay2025-2026.pdf),
[NUS AY2026/2027](https://www.nus.edu.sg/registrar/docs/default-source/calendar/ay2026-2027.pdf),
[MOM public holidays 2026](https://www.mom.gov.sg/newsroom/press-releases/2025/0616-public-holidays-for-2026).
The classification of orientation/special term is a project assumption, not an official demand measurement.

## Synthetic training and evaluation

`generate_training_data.py` creates 12,768 synthetic snapshots: six halls, seven windows per day, January–October 2026.
Random seed 42 makes the CSV reproducible. Every row has `is_synthetic=1`.
Machine counts, known bookings and recent request counts are simulated snapshots, not an imported reservation history.
The assumed demand rate increases with term time, weekends, evenings, recent demand and lead time.
The target is sampled from a Poisson distribution **after** creating the input features. It is not capped at machine capacity:
requests can exceed the supply of available machines.

The pipeline uses DictVectorizer to one-hot encode the hall and retain numeric inputs, then a RandomForestRegressor
(100 trees, maximum depth 12, minimum 4 samples per leaf, random seed 42).
Training uses only windows ending before the 1 September cutoff (all requests arrive before pickup start).
Evaluation uses forecasts made on or after that cutoff; 132 overlapping boundary rows are excluded.
This ensures training targets are already known at evaluation time. No random train/test split is used.
The saved pipeline is the same fitted model that was evaluated, without a subsequent refit on the holdout.

`artifacts/metrics.json` records the exact versions, split boundaries and results:

| Measure | Value |
| --- | ---: |
| Training rows | 10,206 |
| Evaluation rows | 2,430 |
| Random Forest MAE (requests) | 6.58 |
| Historical-average baseline MAE (requests) | 33.53 |

The baseline is the training mean for each hall/pickup hour, with the overall training mean as a fallback.
These are demonstration results against assumed synthetic relationships, **not evidence of accuracy or fairness on real customer demand**.
Real forecasts should later be logged and compared with actual subsequent requests before claiming production validity.

## Pricing rules

`bookings/pricing.py` performs the calculation:

```text
capacity = currently available same-room washer/dryer pairs from C02
pressure = predicted_new_requests / capacity
multiplier = clamp(1 + 0.15 * (pressure - 1), 0.85, 1.25)
machine fee = $2.00 (combined wash and dry)
worker fee = $1.00 * multiplier
platform fee = $1.00 * multiplier
total = machine fee + worker fee + platform fee
```

Capacity must be positive; a price never makes an infeasible window available.
The multiplier is stored to six decimal places. Each fee is rounded to cents with Decimal/ROUND_HALF_UP, then summed.
The total is bounded between $3.70 and $4.50. Missing/corrupt/incompatible models, unknown halls, uncovered calendar dates,
or invalid predictions use multiplier 1.00 and total $4.00. The quote records `used_fallback` and the failure category;
the customer sees a standard-price explanation. Database failures are not disguised as ML failures.

The selected quote stores the price breakdown, prediction, capacity and feature snapshot.
It expires after 15 minutes or at pickup start, whichever comes first. Opening it again does not recalculate the price.
The availability table explicitly shows estimates: the final review price may differ if demand/capacity changes before selection.
Availability remains provisional because only worker acceptance will reserve machines.

## Shared order foundation for C04

`LaundryOrder.quote` is a required OneToOneField. Customer, hall, address, pickup window and fixed prices are obtained
through `order.quote`; the same quote cannot create two orders. `created_at` measures submission time; status initially is `requested`.
Only the small ledger is implemented here. C04 still needs its submission form and transaction, ownership/expiry/address checks,
and another C02 availability check. It must use the stored prices and must not create an order from an expired quote.
P03 still needs atomic machine reservations and a link from reservations to the accepted order.
Coordinate these shared models before extending the later order statuses and worker assignment.

## Main files

- `ml/features.py`: shared feature names and local calendar lookup.
- `ml/generate_training_data.py`: clearly labelled synthetic CSV generator.
- `ml/train_model.py`: preprocessing, training, chronological evaluation and model export.
- `bookings/pricing.py`: live inputs, inference, price calculation and quote saving.
- `bookings/models.py`: PriceQuote snapshot and minimal LaundryOrder ledger.
- `customerstorefront/views.py`: customer-only browsing, quote creation and quote display.

No persistent tests were added at the user's request. Verification used Django checks and disposable in-memory database requests.
