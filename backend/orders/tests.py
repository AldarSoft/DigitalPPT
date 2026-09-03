from django.contrib.auth import get_user_model
from django.test import TestCase
from uuid import uuid4
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from core.models import UserNotification
from licensing.models import License, LicenseEvent, Organization, OrganizationMembership
from licensing.services import OrganizationService
from orders.models import InventoryReservation, Order, OrderItem, Shipment, ShipmentItem
from orders.services import InventoryReservationService, OrderService, ShipmentService
from payments.models import PaymentAttempt, PaymentProvider
from payments.services import PaymentService
from products.models import Category, Product


class AdminManualOrderTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="manual-admin",
            email="manual-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
            is_superuser=True,
        )
        self.client_user = User.objects.create_user(
            username="manual-client",
            email="manual-client@example.com",
            password="StrongPass123!",
            first_name="Manual",
            last_name="Client",
        )
        self.organization = OrganizationService.create(
            name="Manual Order Corp",
            owner=self.client_user,
        )
        category = Category.objects.create(name="Manual products")
        self.license_product = Product.objects.create(
            category=category,
            name="Manual Business License",
            sku="MAN-LIC-200",
            price="1000.00",
            licensing_role=Product.LicensingRole.LICENSE_PRODUCT,
            license_capacity=200,
            license_term_days=365,
            status=Product.Status.PUBLISHED,
        )
        self.physical_product = Product.objects.create(
            category=category,
            name="Manual Radio",
            sku="MAN-RADIO-1",
            price="250.00",
            inventory_quantity=10,
            status=Product.Status.PUBLISHED,
        )
        self.api = APIClient()
        self.api.force_authenticate(self.staff)

    def payload(self, *, product, payment_state, reference=""):
        return {
            "customer_mode": "existing",
            "customer_id": self.client_user.pk,
            "organization_mode": "existing",
            "organization_id": self.organization.pk,
            "payment_state": payment_state,
            "payment_reference": reference,
            "items": [{"product": product.pk, "quantity": 1}],
        }

    def test_draft_has_no_payment_or_provisioning_and_is_hidden_from_client(self):
        response = self.api.post(
            "/api/v1/orders/manual/",
            self.payload(product=self.license_product, payment_state="draft"),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(order_number=response.data["order_number"])
        self.assertEqual(order.status, Order.Status.DRAFT)
        self.assertFalse(PaymentAttempt.objects.filter(order=order).exists())
        self.assertFalse(License.objects.filter(source_order_item__order=order).exists())

        self.api.force_authenticate(self.client_user)
        client_orders = self.api.get("/api/v1/orders/")
        self.assertNotIn(order.order_number, [item["order_number"] for item in client_orders.data["results"]])

    def test_waiting_payment_stays_pending_without_provisioning(self):
        response = self.api.post(
            "/api/v1/orders/manual/",
            self.payload(product=self.license_product, payment_state="waiting_payment"),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(order_number=response.data["order_number"])
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertFalse(PaymentAttempt.objects.filter(order=order).exists())
        self.assertFalse(License.objects.filter(source_order_item__order=order).exists())

    def test_paid_digital_order_completes_and_provisions(self):
        response = self.api.post(
            "/api/v1/orders/manual/",
            self.payload(
                product=self.license_product,
                payment_state="paid",
                reference="BANK-VERIFIED-1001",
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(order_number=response.data["order_number"])
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(order.user, self.client_user)
        self.assertEqual(order.created_by, self.staff)
        self.assertEqual(order.source, Order.Source.ADMIN)
        self.assertTrue(PaymentAttempt.objects.filter(order=order, status="succeeded").exists())
        self.assertTrue(License.objects.filter(source_order_item__order=order).exists())

    def test_admin_organization_choices_are_filtered_to_selected_client(self):
        other_user = get_user_model().objects.create_user(
            username="other-manual-client",
            email="other-manual-client@example.com",
            password="StrongPass123!",
        )
        other_organization = OrganizationService.create(
            name="Other Manual Corp",
            owner=other_user,
        )

        response = self.api.get(
            f"/api/v1/admin/licensing/organizations/?customer_id={self.client_user.pk}"
        )

        self.assertEqual(response.status_code, 200)
        organization_ids = [item["id"] for item in response.data["results"]]
        self.assertIn(self.organization.pk, organization_ids)
        self.assertNotIn(other_organization.pk, organization_ids)

    def test_paid_physical_order_is_scheduled_without_early_stock_deduction(self):
        response = self.api.post(
            "/api/v1/orders/manual/",
            self.payload(
                product=self.physical_product,
                payment_state="paid",
                reference="BANK-VERIFIED-1002",
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(order_number=response.data["order_number"])
        self.assertEqual(order.status, Order.Status.SCHEDULED)
        self.assertFalse(order.stock_deducted)
        reservation = InventoryReservation.objects.get(order_item__order=order)
        self.assertEqual(reservation.status, InventoryReservation.Status.RESERVED)
        self.assertEqual(reservation.quantity, 1)


class InventoryReservationLifecycleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.customer = User.objects.create_user(
            username="reservation-customer",
            email="reservation-customer@example.com",
            password="StrongPass123!",
        )
        category = Category.objects.create(name="Reservation products")
        self.product = Product.objects.create(
            category=category,
            name="Reservation radio",
            sku="RESERVE-RADIO",
            price="250.00",
            inventory_quantity=2,
            status=Product.Status.PUBLISHED,
        )
        self.provider, _ = PaymentProvider.objects.get_or_create(
            code=PaymentProvider.Code.STRIPE,
            defaults={"display_name": "Stripe", "is_enabled": True, "test_mode": True},
        )

    def create_order(self, *, quantity=1):
        order = Order.objects.create(
            user=self.customer,
            source=Order.Source.DIRECT,
            customer_first_name="Reservation",
            customer_last_name="Customer",
            customer_email=self.customer.email,
            shipping_address="1 Main Street",
            shipping_city="Ulaanbaatar",
            shipping_country="Mongolia",
            subtotal=str(250 * quantity),
            total=str(250 * quantity),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            sku=self.product.sku,
            unit_price="250.00",
            quantity=quantity,
            line_total=str(250 * quantity),
        )
        return order

    def pay(self, order):
        attempt = PaymentAttempt.objects.create(
            order=order,
            provider=self.provider,
            amount=order.total,
            currency="USD",
            is_test=True,
            status=PaymentAttempt.Status.PENDING,
            created_by=self.customer,
        )
        return PaymentService.complete_success(
            attempt=attempt,
            actor=self.customer,
            external_reference=f"TEST-{attempt.pk}",
        )

    def test_paid_physical_order_requires_a_shipment_to_consume_stock(self):
        order = self.create_order(quantity=2)
        self.pay(order)

        order.refresh_from_db()
        self.product.refresh_from_db()
        reservation = InventoryReservation.objects.get(order_item__order=order)
        self.assertEqual(order.status, Order.Status.SCHEDULED)
        self.assertFalse(order.stock_deducted)
        self.assertEqual(self.product.inventory_quantity, 2)
        self.assertEqual(reservation.status, InventoryReservation.Status.RESERVED)

        with self.assertRaises(ValidationError):
            OrderService.update_status(order=order, new_status=Order.Status.PROCESSING)

        ShipmentService.create_shipment(
            order_number=order.order_number,
            items=[{"order_item_id": order.items.get().pk, "quantity": 2}],
            actor=self.customer,
        )
        order.refresh_from_db()
        self.product.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertTrue(order.stock_deducted)
        self.assertEqual(self.product.inventory_quantity, 0)
        self.assertEqual(reservation.status, InventoryReservation.Status.CONSUMED)
        self.assertIsNotNone(reservation.consumed_at)

    def test_active_reservation_is_subtracted_from_public_catalog_stock(self):
        order = self.create_order(quantity=1)
        self.pay(order)

        public_response = APIClient().get("/api/v1/products/catalog/reservation-radio/")

        self.assertEqual(public_response.status_code, 200)
        # Public responses carry the sellable availability signal only.
        self.assertEqual(public_response.data["inventory_quantity"], 1)
        self.assertNotIn("on_hand_inventory_quantity", public_response.data)
        self.assertNotIn("reserved_inventory_quantity", public_response.data)
        self.assertNotIn("backordered_inventory_quantity", public_response.data)

        staff = get_user_model().objects.create_user(
            username="catalog-staff",
            email="catalog-staff@example.com",
            password="StrongPass123!",
            is_staff=True,
            is_superuser=True,
        )
        staff_client = APIClient()
        staff_client.force_authenticate(staff)
        staff_response = staff_client.get("/api/v1/products/catalog/reservation-radio/")
        self.assertEqual(staff_response.status_code, 200)
        self.assertEqual(staff_response.data["on_hand_inventory_quantity"], 2)
        self.assertEqual(staff_response.data["reserved_inventory_quantity"], 1)
        self.assertEqual(staff_response.data["inventory_quantity"], 1)

    def test_paid_order_backorders_the_shortage_without_rejecting_payment(self):
        first = self.create_order(quantity=2)
        second = self.create_order(quantity=1)
        self.pay(first)

        attempt = self.pay(second)

        second.refresh_from_db()
        item = second.items.get()
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(second.status, Order.Status.BACKORDERED)
        self.assertEqual(item.reserved_quantity, 0)
        self.assertEqual(item.backordered_quantity, 1)
        self.assertEqual(item.fulfillment_status, OrderItem.FulfillmentStatus.BACKORDERED)
        self.assertFalse(InventoryReservation.objects.filter(order_item__order=second).exists())

    def test_inventory_restock_allocates_the_oldest_backorder_and_schedules_it(self):
        first = self.create_order(quantity=2)
        second = self.create_order(quantity=1)
        self.pay(first)
        self.pay(second)

        self.product.inventory_quantity = 3
        self.product.save(update_fields=["inventory_quantity", "updated_at"])
        changed_orders = InventoryReservationService.reserve_backorders_for_product(
            product_id=self.product.pk
        )

        second.refresh_from_db()
        item = second.items.get()
        reservation = InventoryReservation.objects.get(order_item=item)
        self.assertEqual(changed_orders, [second.pk])
        self.assertEqual(second.status, Order.Status.SCHEDULED)
        self.assertEqual(item.reserved_quantity, 1)
        self.assertEqual(item.backordered_quantity, 0)
        self.assertEqual(item.fulfillment_status, OrderItem.FulfillmentStatus.READY)
        self.assertEqual(reservation.quantity, 1)

    def test_approved_cancellation_releases_an_unfulfilled_reservation(self):
        order = self.create_order(quantity=1)
        self.pay(order)

        OrderService.update_status(
            order=order,
            new_status=Order.Status.CANCELLED,
            allow_paid_cancellation=True,
        )

        reservation = InventoryReservation.objects.get(order_item__order=order)
        self.assertEqual(reservation.status, InventoryReservation.Status.RELEASED)
        self.assertEqual(reservation.release_reason, "Order cancelled before fulfillment.")

    def test_failed_payment_creates_no_reservation(self):
        order = self.create_order(quantity=1)
        attempt = PaymentAttempt.objects.create(
            order=order,
            provider=self.provider,
            amount=order.total,
            currency="USD",
            is_test=True,
            status=PaymentAttempt.Status.PENDING,
            created_by=self.customer,
        )

        attempt.status = PaymentAttempt.Status.FAILED
        attempt.save(update_fields=["status", "updated_at"])

        self.assertFalse(InventoryReservation.objects.filter(order_item__order=order).exists())

    def test_refund_releases_an_unfulfilled_reservation_and_cancels_the_order(self):
        order = self.create_order(quantity=1)
        attempt = self.pay(order)

        PaymentService.mark_refunded(attempt=attempt, reason="Provider refund confirmed.")

        order.refresh_from_db()
        self.product.refresh_from_db()
        reservation = InventoryReservation.objects.get(order_item__order=order)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.REFUNDED)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.product.inventory_quantity, 2)
        self.assertEqual(reservation.status, InventoryReservation.Status.RELEASED)
        self.assertEqual(reservation.release_reason, "Provider refund confirmed.")

    def test_refund_after_partial_shipment_does_not_restore_shipped_stock(self):
        order = self.create_order(quantity=2)
        attempt = self.pay(order)
        item = order.items.get()
        ShipmentService.create_shipment(
            order_number=order.order_number,
            items=[{"order_item_id": item.pk, "quantity": 1}],
            actor=self.customer,
        )

        PaymentService.mark_refunded(attempt=attempt, reason="Partial shipment refund.")

        order.refresh_from_db()
        self.product.refresh_from_db()
        reservation = InventoryReservation.objects.get(order_item=item)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.product.inventory_quantity, 1)
        self.assertEqual(reservation.status, InventoryReservation.Status.RELEASED)


class ShipmentFulfillmentTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="ship-admin",
            email="ship-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
            is_superuser=True,
        )
        self.customer = User.objects.create_user(
            username="ship-customer",
            email="ship-customer@example.com",
            password="StrongPass123!",
            first_name="Ship",
            last_name="Customer",
        )
        category = Category.objects.create(name="Shipment products")
        self.product = Product.objects.create(
            category=category,
            name="Shipment radio",
            sku="SHIP-RADIO",
            price="250.00",
            inventory_quantity=3,
            status=Product.Status.PUBLISHED,
        )
        self.provider, _ = PaymentProvider.objects.get_or_create(
            code=PaymentProvider.Code.STRIPE,
            defaults={"display_name": "Stripe", "is_enabled": True, "test_mode": True},
        )
        self.api = APIClient()
        self.api.force_authenticate(self.staff)

    def create_order(self, *, product=None, quantity=1):
        product = product or self.product
        order = Order.objects.create(
            user=self.customer,
            source=Order.Source.DIRECT,
            customer_first_name="Ship",
            customer_last_name="Customer",
            customer_email=self.customer.email,
            shipping_address="1 Main Street",
            shipping_city="Ulaanbaatar",
            shipping_country="Mongolia",
            subtotal=str(250 * quantity),
            total=str(250 * quantity),
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            sku=product.sku,
            unit_price="250.00",
            quantity=quantity,
            line_total=str(250 * quantity),
        )
        return order

    def pay(self, order):
        attempt = PaymentAttempt.objects.create(
            order=order,
            provider=self.provider,
            amount=order.total,
            currency="USD",
            is_test=True,
            status=PaymentAttempt.Status.PENDING,
            created_by=self.customer,
        )
        return PaymentService.complete_success(
            attempt=attempt,
            actor=self.customer,
            external_reference=f"SHIP-TEST-{attempt.pk}",
        )

    def test_partial_shipment_reduces_on_hand_and_reserved_together(self):
        order = self.create_order(quantity=2)
        self.pay(order)

        with self.captureOnCommitCallbacks(execute=True):
            ShipmentService.create_shipment(
                order_number=order.order_number,
                items=[{"order_item_id": order.items.get().pk, "quantity": 1}],
                carrier="FedEx",
                tracking_number="TRK-001",
                actor=self.staff,
            )

        order.refresh_from_db()
        item = order.items.get()
        self.product.refresh_from_db()
        reservation = InventoryReservation.objects.get(order_item=item)
        self.assertEqual(order.status, Order.Status.SCHEDULED)
        self.assertEqual(self.product.inventory_quantity, 2)
        self.assertEqual(reservation.status, InventoryReservation.Status.RESERVED)
        self.assertEqual(reservation.quantity, 1)
        self.assertEqual(item.reserved_quantity, 1)
        self.assertEqual(item.fulfillment_status, OrderItem.FulfillmentStatus.READY)
        self.assertTrue(order.stock_deducted)

    def test_final_shipment_completes_order_when_nothing_remains(self):
        order = self.create_order(quantity=2)
        self.pay(order)
        item = order.items.get()

        with self.captureOnCommitCallbacks(execute=True):
            ShipmentService.create_shipment(
                order_number=order.order_number,
                items=[{"order_item_id": item.pk, "quantity": 1}],
                actor=self.staff,
            )
            ShipmentService.create_shipment(
                order_number=order.order_number,
                items=[{"order_item_id": item.pk, "quantity": 1}],
                tracking_number="TRK-002",
                actor=self.staff,
            )

        order.refresh_from_db()
        item.refresh_from_db()
        self.product.refresh_from_db()
        reservation = InventoryReservation.objects.get(order_item=item)
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(self.product.inventory_quantity, 1)
        self.assertEqual(reservation.status, InventoryReservation.Status.CONSUMED)
        self.assertEqual(reservation.quantity, 0)
        self.assertEqual(item.reserved_quantity, 0)
        self.assertEqual(item.fulfillment_status, OrderItem.FulfillmentStatus.FULFILLED)

    def test_shipping_one_product_keeps_order_scheduled_while_another_waits(self):
        category = Category.objects.create(name="More shipment products")
        other_product = Product.objects.create(
            category=category,
            name="Shipment antenna",
            sku="SHIP-ANT",
            price="80.00",
            inventory_quantity=1,
            status=Product.Status.PUBLISHED,
        )
        order = self.create_order(quantity=1)
        OrderItem.objects.create(
            order=order,
            product=other_product,
            product_name=other_product.name,
            sku=other_product.sku,
            unit_price="80.00",
            quantity=1,
            line_total="80.00",
        )
        self.pay(order)
        item = order.items.get(product=self.product)
        other_item = order.items.get(product=other_product)

        with self.captureOnCommitCallbacks(execute=True):
            ShipmentService.create_shipment(
                order_number=order.order_number,
                items=[{"order_item_id": item.pk, "quantity": 1}],
                actor=self.staff,
            )

        order.refresh_from_db()
        item.refresh_from_db()
        other_item.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SCHEDULED)
        self.assertEqual(item.fulfillment_status, OrderItem.FulfillmentStatus.FULFILLED)
        self.assertEqual(other_item.fulfillment_status, OrderItem.FulfillmentStatus.READY)

    def test_backordered_line_can_only_ship_reserved_units(self):
        self.product.inventory_quantity = 1
        self.product.save(update_fields=["inventory_quantity", "updated_at"])
        order = self.create_order(quantity=3)
        self.pay(order)
        order.refresh_from_db()
        item = order.items.get()
        self.assertEqual(order.status, Order.Status.BACKORDERED)
        self.assertEqual(item.reserved_quantity, 1)
        self.assertEqual(item.backordered_quantity, 2)

        with self.assertRaises(ValidationError):
            ShipmentService.create_shipment(
                order_number=order.order_number,
                items=[{"order_item_id": item.pk, "quantity": 2}],
                actor=self.staff,
            )

        with self.captureOnCommitCallbacks(execute=True):
            ShipmentService.create_shipment(
                order_number=order.order_number,
                items=[{"order_item_id": item.pk, "quantity": 1}],
                actor=self.staff,
            )

        order.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(order.status, Order.Status.BACKORDERED)
        self.assertEqual(item.fulfillment_status, OrderItem.FulfillmentStatus.BACKORDERED)
        self.assertEqual(item.reserved_quantity, 0)
        self.assertEqual(item.backordered_quantity, 2)

    def test_restock_after_partial_shipment_allocates_and_notifies(self):
        self.product.inventory_quantity = 1
        self.product.save(update_fields=["inventory_quantity", "updated_at"])
        order = self.create_order(quantity=3)
        self.pay(order)
        order.refresh_from_db()
        item = order.items.get()

        with self.captureOnCommitCallbacks(execute=True):
            ShipmentService.create_shipment(
                order_number=order.order_number,
                items=[{"order_item_id": item.pk, "quantity": 1}],
                actor=self.staff,
            )

        self.product.inventory_quantity = 3
        self.product.save(update_fields=["inventory_quantity", "updated_at"])
        with self.captureOnCommitCallbacks(execute=True):
            changed_orders = InventoryReservationService.reserve_backorders_for_product(
                product_id=self.product.pk
            )

        order.refresh_from_db()
        item.refresh_from_db()
        reservation = InventoryReservation.objects.get(order_item=item)
        self.assertEqual(changed_orders, [order.pk])
        self.assertEqual(order.status, Order.Status.SCHEDULED)
        self.assertEqual(reservation.quantity, 2)
        self.assertEqual(reservation.status, InventoryReservation.Status.RESERVED)
        self.assertEqual(item.fulfillment_status, OrderItem.FulfillmentStatus.READY)
        self.assertTrue(
            UserNotification.objects.filter(
                recipient=self.customer,
                title=f"Order {order.order_number} is Ready to ship",
                message__icontains="ready to ship",
            ).exists()
        )
        self.assertTrue(
            UserNotification.objects.filter(recipient=self.staff).exists()
        )

    def test_cannot_ship_unpaid_pending_or_completed_orders(self):
        order = self.create_order(quantity=1)
        item = order.items.get()
        with self.assertRaises(ValidationError):
            ShipmentService.create_shipment(
                order_number=order.order_number,
                items=[{"order_item_id": item.pk, "quantity": 1}],
                actor=self.staff,
            )

        self.pay(order)
        with self.captureOnCommitCallbacks(execute=True):
            ShipmentService.create_shipment(
                order_number=order.order_number,
                items=[{"order_item_id": item.pk, "quantity": 1}],
                actor=self.staff,
            )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)
        with self.assertRaises(ValidationError):
            ShipmentService.create_shipment(
                order_number=order.order_number,
                items=[{"order_item_id": item.pk, "quantity": 1}],
                actor=self.staff,
            )

    def test_shipment_records_carrier_tracking_and_address_snapshot(self):
        order = self.create_order(quantity=2)
        self.pay(order)
        item = order.items.get()

        with self.captureOnCommitCallbacks(execute=True):
            ShipmentService.create_shipment(
                order_number=order.order_number,
                items=[{"order_item_id": item.pk, "quantity": 1}],
                carrier="DHL",
                tracking_number="TRK-DHL-1",
                notes="Fragile",
                actor=self.staff,
            )
            ShipmentService.create_shipment(
                order_number=order.order_number,
                items=[{"order_item_id": item.pk, "quantity": 1}],
                actor=self.staff,
            )

        shipments = list(Shipment.objects.filter(order=order).order_by("pk"))
        self.assertEqual(len(shipments), 2)
        first = shipments[0]
        self.assertTrue(first.shipment_number.startswith("SHP-"))
        self.assertNotEqual(first.shipment_number, shipments[1].shipment_number)
        self.assertEqual(first.carrier, "DHL")
        self.assertEqual(first.tracking_number, "TRK-DHL-1")
        self.assertEqual(first.notes, "Fragile")
        self.assertEqual(first.shipping_address, order.shipping_address)
        self.assertEqual(first.shipping_city, order.shipping_city)
        self.assertEqual(first.shipping_country, order.shipping_country)
        shipment_item = ShipmentItem.objects.get(shipment=first)
        self.assertEqual(shipment_item.quantity, 1)
        self.assertEqual(shipment_item.product_name, item.product_name)
        self.assertEqual(shipment_item.sku, item.sku)

    def test_ship_endpoint_requires_manage_orders_permission(self):
        order = self.create_order(quantity=1)
        self.pay(order)
        item = order.items.get()

        self.api.force_authenticate(self.customer)
        response = self.api.post(
            f"/api/v1/orders/{order.order_number}/ship/",
            {"idempotency_key": str(uuid4()), "items": [{"order_item_id": item.pk, "quantity": 1}]},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

        self.api.force_authenticate(self.staff)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.api.post(
                f"/api/v1/orders/{order.order_number}/ship/",
                {"idempotency_key": str(uuid4()), "items": [{"order_item_id": item.pk, "quantity": 1}]},
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], Order.Status.COMPLETED)
        self.assertEqual(len(response.data["shipments"]), 1)
        self.assertEqual(response.data["shipments"][0]["items"][0]["quantity"], 1)

    def test_ship_endpoint_rejects_duplicate_item_lines(self):
        order = self.create_order(quantity=2)
        self.pay(order)
        item = order.items.get()

        response = self.api.post(
            f"/api/v1/orders/{order.order_number}/ship/",
            {
                "idempotency_key": str(uuid4()),
                "items": [
                    {"order_item_id": item.pk, "quantity": 1},
                    {"order_item_id": item.pk, "quantity": 1},
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("only once", str(response.data))

    def test_ship_endpoint_retry_with_same_key_creates_one_shipment(self):
        order = self.create_order(quantity=1)
        self.pay(order)
        item = order.items.get()
        key = str(uuid4())
        payload = {
            "idempotency_key": key,
            "items": [{"order_item_id": item.pk, "quantity": 1}],
        }

        first = self.api.post(
            f"/api/v1/orders/{order.order_number}/ship/", payload, format="json"
        )
        second = self.api.post(
            f"/api/v1/orders/{order.order_number}/ship/", payload, format="json"
        )

        self.product.refresh_from_db()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(Shipment.objects.filter(order=order).count(), 1)
        self.assertEqual(self.product.inventory_quantity, 2)

    def test_update_status_rejects_processing_or_completed_with_backorders(self):
        self.product.inventory_quantity = 1
        self.product.save(update_fields=["inventory_quantity", "updated_at"])
        order = self.create_order(quantity=3)
        self.pay(order)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.BACKORDERED)

        with self.assertRaises(ValidationError):
            OrderService.update_status(order=order, new_status=Order.Status.PROCESSING)
        with self.assertRaises(ValidationError):
            OrderService.update_status(order=order, new_status=Order.Status.COMPLETED)

    def test_legacy_consume_marks_partially_ready_item_as_backordered(self):
        self.product.inventory_quantity = 1
        self.product.save(update_fields=["inventory_quantity", "updated_at"])
        order = self.create_order(quantity=3)
        self.pay(order)
        order.refresh_from_db()
        item = order.items.get()

        consumed = InventoryReservationService.consume_for_order(order=order)

        self.assertTrue(consumed)
        item.refresh_from_db()
        self.product.refresh_from_db()
        reservation = InventoryReservation.objects.get(order_item=item)
        self.assertEqual(self.product.inventory_quantity, 0)
        self.assertEqual(item.reserved_quantity, 0)
        self.assertEqual(item.backordered_quantity, 2)
        self.assertEqual(item.fulfillment_status, OrderItem.FulfillmentStatus.BACKORDERED)
        self.assertEqual(reservation.status, InventoryReservation.Status.CONSUMED)
        self.assertEqual(reservation.quantity, 0)


class AdminOrganizationCreationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="organization-admin",
            email="organization-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
            is_superuser=True,
        )
        self.api = APIClient()
        self.api.force_authenticate(self.staff)

    def test_draft_organization_has_no_owner(self):
        response = self.api.post(
            "/api/v1/admin/licensing/organizations/",
            {"name": "Future Corp", "owner_mode": "draft"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        organization = Organization.objects.get(pk=response.data["id"])
        self.assertEqual(organization.status, Organization.Status.DRAFT)
        self.assertFalse(organization.memberships.exists())

    def test_owner_invitation_activates_draft_when_accepted(self):
        response = self.api.post(
            "/api/v1/admin/licensing/organizations/",
            {"name": "Invited Corp", "owner_mode": "invite", "owner_email": "owner-invite@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        organization = Organization.objects.get(pk=response.data["id"])
        self.assertEqual(organization.status, Organization.Status.DRAFT)
        token = response.data["invitation"]["accept_url"].split("token=", 1)[1]
        owner = get_user_model().objects.create_user(
            username="owner-invite",
            email="owner-invite@example.com",
            password="StrongPass123!",
        )
        self.api.force_authenticate(owner)
        accepted = self.api.post(
            "/api/v1/licensing/organization/invitations/accept/",
            {"token": token},
            format="json",
        )
        self.assertEqual(accepted.status_code, 200)
        organization.refresh_from_db()
        self.assertEqual(organization.status, Organization.Status.ACTIVE)
        self.assertEqual(organization.memberships.get(role="owner").user, owner)

    def test_staff_can_assign_the_initial_owner_from_a_draft_license_manager(self):
        manager = get_user_model().objects.create_user(
            username="draft-manager",
            email="draft-manager@example.com",
            password="StrongPass123!",
        )
        organization = OrganizationService.create_draft(
            name="Owner Assignment Corp",
            created_by=self.staff,
        )
        membership = OrganizationMembership.objects.create(
            organization=organization,
            user=manager,
            role=OrganizationMembership.Role.LICENSE_MANAGER,
        )

        response = self.api.post(
            f"/api/v1/admin/licensing/organizations/{organization.pk}/users/ownership-transfer/",
            {"membership_id": membership.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        organization.refresh_from_db()
        membership.refresh_from_db()
        self.assertEqual(organization.status, Organization.Status.ACTIVE)
        self.assertEqual(membership.role, OrganizationMembership.Role.OWNER)
        event = LicenseEvent.objects.get(organization=organization)
        self.assertTrue(event.metadata["initial_owner_assigned"])
        self.assertIsNone(event.metadata["previous_owner_id"])
