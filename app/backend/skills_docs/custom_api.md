# Backend Custom API

## Description
Backend custom API development with FastAPI. Covers service logic implementation under services/, API endpoint routing under routers/, automatic routing, environment variables, and a complete Stripe payment integration example including create_payment_session and verify_payment.

## Guide

## Backend Custom API Integration
- Implement the service logic of custom functions under `./app/backend/services/`
- Define api endpoint routing and implement it under `./app/backend/routers/`. Import the necessary ORM files under `./app/backend/models/` and the necessary logic files under `./app/backend/services/`
- Since automatic routing has been added, there is no need to add api route manually
- Frontend MUST call custom routers through `metagptx/web-sdk@latest` with `client.apiCall.invoke(...)`; see `./app/backend/skills_docs/web_sdk.md` for frontend rules and examples
  - Pass only the route path such as `/api/v1/payment/create_payment_session`
  - Do NOT use `fetch`, `axios`, `getAPIBaseURL`, `VITE_API_BASE_URL`, `http://localhost`, or `http://127.0.0.1`
- To obtain environment variables from os environ, must use like `import os\nstripe_key = os.environ.get("STRIPE_SECRET_KEY")  # Pay attention to capitalization
- If installed new backend packages, append them to the `./app/backend/requirements.txt`
- Follow the existing backend import conventions used by nearby router files. For database/auth dependencies, use `from core.database import get_db` and `from dependencies.auth import get_current_user` (or `get_admin_user`) as appropriate.
- If you create or modify backend Python files for this custom API work, run `python -m py_compile` on the changed Python files before finishing. If it fails, fix the errors.

### Database Session Boundaries For Slow External Work

- If a route or service does both database work and a slow external step such as `AIHubService`, Stripe, ObjectStorage, `httpx`, or any third-party API/file processing, do NOT keep an active SQLAlchemy transaction open during the slow step.
- `AsyncSession` transactions reopen on normal `refresh()` and `select()` calls. Do not `commit()` and then `refresh()` or `select()` before a long external call unless you end that new transaction again.
- Preferred shape: short DB phase -> `commit()` or `rollback()` to end the current transaction -> slow external call -> fresh DB query/update -> `commit()`.
- If only reads happened and no pending writes remain, use `await db.rollback()` before the slow external call. Connection pool settings do not fix an already-open transaction waiting on a long call.

```python
credits = await deduct_credits(db, current_user.id, 1, "generate")
remaining = credits.credits
await db.rollback()  # close the transaction before the slow external call

payload = await run_slow_ai_or_http_call(data.topic)

record = Result(user_id=current_user.id, payload_json=json.dumps(payload))
db.add(record)
await db.commit()
```

### Requirement-Critical Rules

#### Payment And Billing Requirements
- If the user requirement includes explicit pricing, paid upgrade, subscription, billing, checkout, or one-time purchase, you MUST implement a real payment flow. A billing surface, plan badge, quota text, or "Upgrade" button alone does NOT satisfy the requirement.
- Before implementing payment, decide and document the purchase path and entitlement model: what the user is buying, where checkout starts, which frontend routes handle success/cancel, which backend route creates checkout, which backend route verifies it, and which backend-owned state changes after verification.
- If the billing UX is specified, follow it. Otherwise, choose the simplest product-appropriate pattern.
- A real payment flow must include at least one frontend checkout entry that is reachable through the intended purchaser flow, a backend `create_payment_session` route, a backend `verify_payment` route, and a frontend success path that reads `session_id` and calls the verify endpoint.
- Payment-related business state such as quota, plan, credits, subscription status, or paid entitlements MUST be updated only after backend verification succeeds. Do not change those fields directly from the frontend or show a paid state before verification.
- Per-user singleton business state such as quotas, credits, subscriptions, paid entitlements, onboarding rows, or settings must be created and read idempotently. If singleton uniqueness is not guaranteed by schema, do not rely on `scalar_one_or_none()` as the only read path for requirement-critical flows.
- When payment is explicitly required, do not replace checkout with shortcut endpoints like `/upgrade-to-pro`, mark the billing flow as complete when the UI cannot actually reach checkout, or create a cyclic paywall that blocks users from reaching checkout.
- Do not hide the only purchase path behind an obscure or exhausted-state-only entry unless that information architecture is explicitly required by the product design.
- When creating a Stripe checkout session, NEVER pass an empty string as `customer_email`.
- If no validated email is available, omit `customer_email` entirely and let Stripe collect it on the hosted checkout page. Do not send frontend placeholders such as `user?.email || ""` into payment APIs.
- The backend must derive authoritative pricing, subscription tier, credit pack size, or order amount from server-side config or validated product identifiers. Do not trust a frontend-submitted final amount as the source of truth for charge creation.

#### Free Trial, Quota, And Singleton State
- If the requirement promises signup bonus, free trial, gifted credits, or initial quota, implement it as backend-owned per-user state. Marketing copy alone does NOT satisfy the requirement.
- Reuse one idempotent helper such as `get_or_create_quota(user_id)` across quota reads, the core generate/analyze/upload API, payment verification, and any other path that touches the same state.
- Do not create a missing quota row with different defaults in different routers. A promised free trial must not disappear just because the row was first created from a payment or dashboard path.

#### Request And Response Contract Consistency
- For requirement-critical custom APIs, keep frontend request keys, backend Pydantic schema fields, helper/service function parameters, and response keys consistent end-to-end.
- When renaming a field or status key, update every caller and reader in the same bounded flow before considering the task complete. Do not leave mismatches such as `ok` vs `allowed`, `items` vs `order_items`, or a frontend expecting `response.data.id` while the backend returns a different key.
- Do not assume nearby layers will tolerate missing, extra, or renamed fields. If a key is required for the core flow, validate it explicitly before returning success.

#### AI-Backed Custom API Rules
- If a primary custom API returns structured AI content for a core feature, do NOT rely on a single naked `json.loads(raw_content)` path.
- At minimum, extract the JSON block when wrappers may exist, validate required fields before persisting or returning the result, retry or repair once when parsing fails, and return a clear user-facing error instead of a silent reset or fake success.
- If AI is used as a strict classifier or validator for business logic, do not treat parse failure as a business-negative result by default. Add a fallback path or return an explicit temporary failure instead.

#### Acceptance Checklist Before Finishing
- Can the user trigger the custom API from a visible requirement-related UI action, and does the backend perform the real business action instead of only changing UI labels?
- If payment is required, can the user reach checkout and return through verification before any paid state is granted?
- If payment is required, is the chosen purchase path reachable through the intended purchaser flow without guessing hidden affordances, unless the product design explicitly requires that IA?
- If payment is required, does the backend derive the authoritative charge configuration and entitlement update instead of trusting a frontend final amount or paid flag?
- Do frontend request keys, backend schema fields, helper/service params, and response keys match exactly across the same core flow?
- If AI structured output or singleton quota/subscription state is part of the core flow, does it fail safely and work for both first-time and returning users?
- Do all quota/subscription creation paths reuse the same initializer and defaults instead of creating slightly different missing-row behavior in different routers?
- Does any backend route keep a SQLAlchemy transaction open across `AIHubService`, Stripe, ObjectStorage, or another slow external call? If yes, split it into separate DB phases before finishing.

### Backend Example Code
```python
# @File: backend/routers/payments.py
# @Desc: api route for payment example
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import stripe

from core.database import get_db
from dependencies.auth import get_current_user
from schemas.auth import UserResponse
from models.orders import Orders
from core.config import settings

stripe.api_key = settings.stripe_secret_key  # Configure Stripe Key

router = APIRouter(prefix="/api/v1/payment", tags=["payment"])  # prefix MUST starts with "/api/v1"

class CheckoutSessionRequest(BaseModel):
    success_url: str
    cancel_url: str

class CheckoutSessionResponse(BaseModel):
    session_id: str
    url: str

class PaymentVerificationRequest(BaseModel):
    session_id: str

class PaymentStatusResponse(BaseModel):
    status: str
    order_id: int = None
    payment_status: str

@router.post("/create_payment_session", response_model=CheckoutSessionResponse)
async def create_payment_session(
    data: CheckoutSessionRequest,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    "Create a Stripe checkout session from the user's cart items"
    try:
        # Get frontend host
        frontend_host = request.headers.get("App-Host")  # Check if it starts with https/http, must be "App-Host" if you want to get frontend host
        if frontend_host and not frontend_host.startswith(("http://", "https://")):
            # Default to add https
            frontend_host = f"https://{frontend_host}"
        # [CRITICAL] Implementation Steps
        # 1. Validates the cart items and calculates the total amount
        # 2. Creates a new order in the database with status "pending"
        line_items = []  # collect cart items except for the image_url of the item
        # 3. Create Stripe checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,
            mode="payment",
            success_url=f"{frontend_host}/payment-success?session_id={{CHECKOUT_SESSION_ID}}",  # Frontend url to receive checkout session id
            cancel_url=f"{frontend_host}/checkout",  # Frontend url to redirect when cancel payment
            metadata={
                "order_id": str(order.id),
                "user_id": current_user.id
            }  # used to store metadata
        )  # Frontend must contain success_url(params should be `session_id={CHECKOUT_SESSION_ID}`) and cancel_url
        # 4. Save session_id into order. [CRITICAL] If the model has auto-managed `created_at` / `updated_at`,
        #    do not update them manually here; only persist business fields such as session_id or status.
        # 5. Return session_id and sesssion_url to the frontend. 
        return CheckoutSessionResponse(
            session_id=session.id,
            url=session.url
        )
    except Exception as e:
        logging.error(f"Payment session creation error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create payment session, error: {str(e)}")

@router.post("/verify_payment", response_model=PaymentStatusResponse)
async def verify_payment(
    data: PaymentVerificationRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    "Verify payment status and update order"
    try:
        # [CRITICAL] Implementation Steps
        # 1. Retrieve the session from Stripe
        session = stripe.checkout.Session.retrieve(data.session_id)
        order_id = session.metadata.get("order_id")
        # 2. Update order's payment status
        status_mapping = {"complete": "paid", "open": "pending", "expired": "cancelled"}
        status = status_mapping.get(session.status, "pending")
        # 3. Return payment status to the frontend
        return PaymentStatusResponse(
            status=status,
            order_id=int(order_id),
            payment_status=session.payment_status
        )
    except Exception as e:
        logging.error(f"Payment verification error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to verify payment, error: {str(e)}")
```
