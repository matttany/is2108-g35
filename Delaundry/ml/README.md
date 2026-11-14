# C03: demand forecasts and price quotes

## Run locally

From the repository root, activate your virtual environment and run:

```powershell
python -m pip install -r requirements.txt
cd Delaundry
python manage.py migrate
python manage.py runserver
```

New customers select their hall, block and unit during registration. The block must have an active laundry room in the selected hall.
Existing customers with no saved block are directed to `/accounts/block/` before they can browse pickup times.
Log in as a customer with a saved residence and block, then visit http://127.0.0.1:8000/storefront/availability/.
Only machines in the customer's saved block are considered; URL/form parameters cannot select another block.
The table shows estimates; **Review price quote** recalculates the final price on the server and saves it.
The resulting `/storefront/quotes/<id>/` page shows the saved amount and expiry.
Only the customer who created the quote can view it.
Creating a quote does not submit an order, charge money or reserve machines.
On a valid quote, **Submit request** creates an order at the saved price. The page then displays its order number and `Requested` status.

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

Each row predicts the number of **new requests between the forecast time and pickup start**, for one hall/block/window.
Existing bookings are an input, not part of this target.

| Feature | Live source |
| --- | --- |
| residence | CustomerProfile.residence.name; never a customer-supplied hall parameter |
| block | CustomerProfile.block, selected at registration or through the authenticated block form |
| weekday | Pickup date in Singapore time; Monday = 0 |
| pickup_hour | Start of the two-hour service window, 08:00 through 20:00 |
| is_term_time | Local academic_calendar.csv |
| is_public_holiday | Local public_holidays.csv |
| lead_hours | Hours between the current time and pickup start |
| recent_requests | LaundryOrder submissions for the same hall and block in the preceding 24 hours, including later cancellations |
| known_bookings | Reserved washers in that hall/block/date/window; dryers are not counted a second time |
| operational_machines | ACTIVE washers and dryers in the saved block's active room and active hall |

No name, email, unit number or user ID enters the model. The quote separately stores the customer and address for ownership and later order submission.
Without orders, recent_requests correctly stays zero. The optional demo orders contribute to their own block's count for 24 hours after creation.
Quote views and quote creation do not count as requests.

Calendar coverage is **1 January–31 December 2026**, including observed public holidays. Dates outside that range use neutral pricing until both CSVs are extended.
For this regular-undergraduate prototype, term includes teaching, recess, reading, examinations and orientation week. Special term is classified as vacation.
Public holidays are separate from term/vacation, so both flags can be 1. NUS Well-Being Days are not national public holidays and are not included in that flag.

Sources: [NUS AY2025/2026](https://www.nus.edu.sg/registrar/docs/default-source/calendar/ay2025-2026.pdf),
[NUS AY2026/2027](https://www.nus.edu.sg/registrar/docs/default-source/calendar/ay2026-2027.pdf),
[MOM public holidays 2026](https://www.mom.gov.sg/newsroom/press-releases/2025/0616-public-holidays-for-2026).
The classification of orientation/special term is a project assumption, not an official demand measurement.

## Synthetic training and evaluation

`generate_training_data.py` creates 12,768 synthetic snapshots: six halls, seven windows per day, January–October 2026.
Each snapshot samples one block (A–F) within that hall. Machine counts and demand are simulated at block scope, not hall scope.
Random seed 42 makes the CSV reproducible. Every row has `is_synthetic=1`.
Machine counts, known bookings and recent request counts are simulated snapshots, not an imported reservation history.
The assumed demand rate increases with term time, weekends, evenings, recent demand and lead time.
The target is sampled from a Poisson distribution **after** creating the input features. It is not capped at machine capacity:
requests can exceed the supply of available machines.

The pipeline uses DictVectorizer to one-hot encode the hall and block and retain numeric inputs, then a RandomForestRegressor
(100 trees, maximum depth 12, minimum 4 samples per leaf, random seed 42).
Training uses only windows ending before the 1 September cutoff (all requests arrive before pickup start).
Evaluation uses forecasts made on or after that cutoff; 146 overlapping boundary rows are excluded.
This ensures training targets are already known at evaluation time. No random train/test split is used.
The saved pipeline is the same fitted model that was evaluated, without a subsequent refit on the holdout.

`artifacts/metrics.json` records the exact versions, split boundaries and results:

| Measure | Value |
| --- | ---: |
| Training rows | 10,206 |
| Evaluation rows | 2,416 |
| Random Forest MAE (requests) | 2.29 |
| Historical-average baseline MAE (requests) | 5.55 |

The baseline is the training mean for each hall/block/pickup hour, with the overall training mean as a fallback.
These are demonstration results against assumed synthetic relationships, **not evidence of accuracy or fairness on real customer demand**.
Real forecasts should later be logged and compared with actual subsequent requests before claiming production validity.

## Pricing rules

`bookings/pricing.py` performs the calculation:

```text
capacity = currently available washer/dryer pairs in the customer's saved block from C02
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

The selected quote stores the hall, block, unit, price breakdown, prediction, capacity and feature snapshot.
Changing a customer's block later does not rewrite old quotes. Historical quotes without a block are labelled as needing replacement.
It expires after 15 minutes or at pickup start, whichever comes first. Opening it again does not recalculate the price.
Once a quote has been submitted as an order, its page shows that order's status and saved prices instead of an expiry warning.
Expiry still prevents submitting an unused quote; it does not cancel an existing order.
The availability table explicitly shows estimates: the final review price may differ if demand/capacity changes before selection.
Availability remains provisional until submission successfully reserves a washer and dryer. Worker acceptance subsequently confirms the request.

## C04: review and submit a request

`LaundryOrder.quote` is a required OneToOneField. Customer, hall, block, unit, pickup window and fixed prices are obtained
through `order.quote`; the same quote cannot create two orders. `created_at` measures submission time; status initially is `requested`.
The review page shows the saved residence, block, unit, pickup window, delivery deadline and final price.
Its CSRF-protected form posts to `/storefront/quotes/<id>/submit/`. Only an active customer who owns the quote may submit it.
Submission checks the quote is unexpired, has a block and matches the customer's current saved address.
It rechecks C02 availability using the quote's saved hall, block, date and window, then checks expiry again.
In one transaction it creates the requested order and two reserved MachineReservation rows, one available washer and one dryer in the same room.
Each reservation uses `order=order` and the quote's date/window start, holding the machine for the full two-hour window.
No assignment is supplied. If either reservation fails, the transaction rolls back the order and both reservation writes, and the customer receives an availability/retry message.
The order references the existing quote; its price is not recalculated from the model or accepted from browser form values.
No payments or worker assignments are created during submission.

Repeated submission of the same quote returns its existing order, even if the quote later expired or the order was cancelled.
Repeated submissions do not create additional reservations. The database OneToOne constraint prevents duplicate orders,
and the unique reserved-machine/date/window constraint prevents double reservation. Row locks are used on databases that support them;
SQLite lock contention produces a retry message. An unused expired/invalid quote cannot create an order.
The saved quote page displays the order's status after submission and explains that `requested` is not yet `confirmed`.

Call `get_available_windows(profile.residence, service_date, profile.block)`; the block argument is required.
P03 must reuse the order's existing reservations rather than allocate a second pair; only successful eligible worker acceptance should change the order to `confirmed`.
C02 counts all reserved rows, regardless of order status. C03 likewise counts reserved washers, so requested orders already reduce availability and contribute to known bookings.
C07 must release an order's reserved rows when cancelling, including cancellation before worker acceptance, in the same transaction as the status change.
There is no separate capacity-slot model.

Integration prerequisite: the teammate owns `MachineReservation.order` (nullable FK to LaundryOrder, PROTECT, related_name="reservations") and its migration.
The submission code uses that contract; it cannot run successfully until the shared field is merged and its migration applied.
No separate field/migration was created here. Verify the real integrated schema after merging it.

## Three demo orders for collaboration

From `Delaundry`, run:

```powershell
python manage.py migrate
python manage.py seed_demo_orders
```

This adds the following customers and requested orders to your own database, using available windows tomorrow:

| Username | Hall | Block | Unit |
| --- | --- | --- | --- |
| demo_block_1 | Temasek | A | #01-01 |
| demo_block_2 | Temasek | A | #01-02 |
| demo_block_3 | Temasek | B | #01-03 |

Each customer has one saved price quote and one `requested` order. No machine reservations are created.
These older demo records bypass the submission flow and are not reservation-complete examples for P03.
Use a freshly submitted customer request to exercise the new reservation contract; existing demo orders are not automatically backfilled.
Re-running the command keeps those orders, statuses and original dates; it does not duplicate or refresh them.
If a required block has no availability or a demo identity conflicts with another account, all inserts are rolled back.
To use a different hall on the first run, supply its code, e.g. `python manage.py seed_demo_orders --residence eusoff`.
Changing the hall after seeding produces a clear conflict rather than moving existing orders.

All three demo customers use the shared password `peepeepoopoo`. Log in using
`demo_block_1@u.nus.edu`, `demo_block_2@u.nus.edu` or `demo_block_3@u.nus.edu`.
Running `seed_demo_orders` also sets this password on existing demo accounts, without duplicating their orders.
Django stores the password as a hash. These are dummy identities; no email is sent.
Your collaborator should run the seed command locally after pulling the code and applying migrations. Do not share `db.sqlite3` through Git.

To inspect the orders in `python manage.py shell`:

```python
from bookings.models import LaundryOrder
list(LaundryOrder.objects.filter(quote__customer__username__startswith="demo_block_").values(
    "id", "status", "quote__customer__username", "quote__residence__name",
    "quote__block", "quote__service_date", "quote__window_start", "quote__total",
))
```

## C05: customer order history and tracking

Customers can open **My orders** from their home page or the storefront navigation.
`/storefront/orders/` lists only the signed-in customer's orders, including previous and cancelled requests, newest submissions first (10 per page).
`/storefront/orders/<id>/` displays the saved pickup address/window, delivery deadline, fixed price, order status and progress timeline.
Other customers receive 404 for that detail URL; workers cannot access these customer pages. Both routes are read-only GET endpoints.
Quote pages link to their submitted order's tracking page.

Worker details and acceptance time come from `JobAssignment.worker` and `accepted_at` after P03 acceptance.
Recorded machine activity comes from the assignment's `MachineSession` rows: start, expected end and actual end are shown separately.
Washing/drying timeline timestamps use the first recorded start for that cycle type. Expected end times are never treated as actual completion.
Passing a pickup/delivery time does not change status or fabricate progress. Viewing tracking does not reprice orders or modify reservations.

The timeline lists Requested, Confirmed, Picked up, Washing, Drying, Out for return and Delivered, plus cancellation/rejection when applicable.
For stopped orders, only actual timestamp records establish earlier progress; missing history is labelled as unrecorded.
P04 supplies `picked_up_at`, `out_for_return_at` and the collection/washing/drying/return statuses.
P05 supplies `JobAssignment.completed_at` and the `delivered` status. The timeline reads these recorded timestamps;
there is no cancellation/rejection timestamp yet. Progress changes remain restricted to the assigned worker's server-side operations.

## P05: delivery proof and task completion

After P04 finishes drying, the assigned worker opens **My tasks** (`/worker/my-tasks/`) and selects **Record delivery**.
The upload/receipt URL is `/worker/my-tasks/<assignment_id>/delivery/` (assignment ID, not order ID).
Upload one JPEG or PNG photo, up to 5 MiB and 12 million pixels, with an optional note of up to 500 characters.
The server decodes and re-encodes the image, removes metadata, and uses a generated filename. Unsupported/corrupt images are rejected.

`bookings.delivery.complete_delivery(user_id, assignment_id, photo, note="")` rechecks the active, approved assigned worker;
`is_available` is not required for finishing existing jobs. It requires `out_for_return`, recorded collection/return preparation,
exactly one completed 30-minute washer session followed by one completed 30-minute dryer session, and this order's reserved pair
in the quote's room/block/date/window. A late delivery may still be recorded truthfully; times are never backdated to the deadline.

The operation owns a durable database transaction: it saves `DeliveryProof`, sets `JobAssignment.completed_at` and changes the order to
`delivered` together. Do not wrap this service in another atomic block. A failed database write rolls back completion and removes a photo
already saved by that attempt. Storage failures are shown as retry messages. The database and filesystem are separate systems, so an abrupt
process crash can still leave an orphan file; deployment backups/maintenance should cover private uploads as well as the database.

`DeliveryProof.assignment` is one-to-one (`assignment.delivery_proof`), giving one immutable proof per order through `assignment.order`.
It records `photo`, `note`, `uploaded_by` and `uploaded_at`. Assignment completion is represented by non-null `completed_at`, rather than
duplicating the order status. Repeated submissions reuse the original proof, timestamp and note. Reservations remain `reserved` for the
full two-hour window; completion does not release them or change the saved price/payout. `WindowAllocation` remains unused.

Photos live under `PRIVATE_PROOF_ROOT` (default `Delaundry/private_uploads/`), which is ignored by its own `.gitignore`.
Never serve that directory using a public media route or web-server alias. The protected GET endpoint
`/bookings/delivery-proofs/<proof_id>/photo/` authorizes the active owning customer, assigned worker or staff on every request and sends
private/no-store responses. Templates use this route instead of `photo.url`.

Setup from the repository root:

```powershell
python -m pip install -r requirements.txt
cd Delaundry
python manage.py migrate
python manage.py runserver
```

Migration `0010_add_delivery_proof` depends on P04's `0009_add_drying_and_return_progress`. Existing demo orders still need to go through
acceptance and P04 before they can be delivered; do not bypass stages just to make the upload button appear.

## C06: customer delivery proof

Open **My orders**, then an order at `/storefront/orders/<order_id>/`. Its **Delivery proof** section displays the return photo,
optional note, uploader name (or username) and upload time in Singapore time. Selecting the photo opens the protected full image.
Pending orders show a no-proof message. Historical delivered orders without proof show that evidence is unavailable, rather than inventing it.

The customer view first checks order ownership, then loads `DeliveryProof` through that order's assignment. Both the order details and
photo response are private/no-store. Notes are escaped as text; no filesystem path or public upload URL appears in the page.
Viewing proof does not change order status, price or reservations. Image validation and verified completion remain P05's responsibility.
C06 reuses migration `0010_add_delivery_proof`; it adds no further model changes or migrations.

## Main files

- `ml/features.py`: shared feature names and local calendar lookup.
- `ml/generate_training_data.py`: clearly labelled synthetic CSV generator.
- `ml/train_model.py`: preprocessing, training, chronological evaluation and model export.
- `bookings/pricing.py`: live inputs, inference, price calculation and quote saving.
- `bookings/models.py`: PriceQuote snapshot and minimal LaundryOrder ledger.
- `customerstorefront/views.py`: customer-only availability, quotes, submission, order history and details.
- `customerstorefront/tracking.py`: read-only status timeline based on stored status and timestamps.

No persistent tests were added at the user's request. Verification used Django checks and disposable in-memory database requests.
