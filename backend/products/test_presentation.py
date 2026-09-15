from copy import deepcopy

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import SiteSetting
from core.serializers import AdminSiteSettingSerializer
from products.models import Category, Product
from products.presentation import default_product_presentation
from products.serializers import ProductSerializer, ProductWriteSerializer


class PresentationTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Radios')
        self.product = Product.objects.create(category=self.category, name='Test radio', sku='TEST', price=100, detail_layout='radio', status='published')

    def test_defaults_follow_site_changes_but_custom_sections_do_not(self):
        settings = SiteSetting.get_solo()
        custom = deepcopy(settings.product_presentation_defaults['assurances'])
        custom[0]['title'] = 'Custom delivery'
        self.product.presentation_overrides = {'assurances': custom}
        self.product.save()
        settings.product_presentation_defaults['radio']['intro']['heading'] = 'Updated heading'
        settings.product_presentation_defaults['assurances'][0]['title'] = 'Updated delivery'
        settings.save()
        content = ProductSerializer(self.product).data['presentation']
        self.assertEqual(content['intro']['heading'], 'Updated heading')
        self.assertEqual(content['assurances'][0]['title'], 'Custom delivery')
        reset = ProductWriteSerializer(self.product, data={'presentation_overrides': {}}, partial=True)
        self.assertTrue(reset.is_valid(), reset.errors)
        reset.save()
        self.assertEqual(ProductSerializer(self.product).data['presentation']['assurances'][0]['title'], 'Updated delivery')

    def test_empty_override_hides_features_and_omission_preserves_it(self):
        serializer = ProductWriteSerializer(self.product, data={'presentation_overrides': {'features': []}}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        serializer = ProductWriteSerializer(self.product, data={'name': 'Renamed'}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.assertEqual(ProductSerializer(self.product).data['presentation']['features'], [])

    def test_invalid_partial_content_is_rejected_without_modifying_product(self):
        item = default_product_presentation()['assurances'][0]
        for overrides in ({'intro': {}}, {'features': [{'id': 'x'}]}, {'features': [{**item, 'icon': 'unknown'}]}, {'features': [item, item]}, {'arbitrary': []}, {'assurances': [{**item, 'id': 'unknown'}]}):
            serializer = ProductWriteSerializer(self.product, data={'presentation_overrides': overrides}, partial=True)
            self.assertFalse(serializer.is_valid(), overrides)
        self.product.refresh_from_db()
        self.assertEqual(self.product.presentation_overrides, {})

    def test_global_defaults_require_complete_valid_content(self):
        for value in ({}, {'radio': {}}, {**default_product_presentation(), 'accessory': {}}):
            serializer = AdminSiteSettingSerializer(SiteSetting.get_solo(), data={'product_presentation_defaults': value}, partial=True)
            self.assertFalse(serializer.is_valid(), value)

    def test_highlight_limit_and_ordered_content_round_trip(self):
        specs = [{'key': f'Key {i}', 'value': str(i), 'sort_order': i, 'show_in_highlights': True} for i in range(5)]
        serializer = ProductWriteSerializer(self.product, data={'specifications': specs}, partial=True)
        self.assertFalse(serializer.is_valid())
        specs[-1]['show_in_highlights'] = False
        badges = default_product_presentation()['assurances'][::-1]
        badges[0]['active'] = False
        serializer = ProductWriteSerializer(self.product, data={'specifications': specs, 'presentation_overrides': {'assurances': badges}}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        payload = ProductSerializer(self.product).data
        self.assertEqual(sum(s['show_in_highlights'] for s in payload['specifications']), 4)
        self.assertEqual(payload['presentation']['assurances'][0]['id'], 'payment')
        self.assertFalse(payload['presentation']['assurances'][0]['active'])
        self.assertNotIn('presentation_overrides', payload)


class PublishingBoundaryTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name='Catalog')
        self.product = Product.objects.create(category=category, name='Draft product', sku='DRAFT', price=100, is_featured=True)
        self.customer = get_user_model().objects.create_user(username='customer', email='customer@example.com')
        self.staff = get_user_model().objects.create_user(username='inventory', email='inventory@example.com', is_staff=True)
        self.staff.user_permissions.add(Permission.objects.get(codename='manage_inventory'))
        self.superuser = get_user_model().objects.create_user(username='super', email='super@example.com', is_staff=True, is_superuser=True)

    def test_unpublished_products_are_hidden_for_every_public_viewer(self):
        for user in (None, self.customer, self.staff, self.superuser):
            client = APIClient()
            client.force_authenticate(user)
            for status, active in (('draft', True), ('archived', True), ('published', False)):
                Product.objects.filter(pk=self.product.pk).update(status=status, is_active=active)
                for query in ('', '?featured=true', '?search=Draft', '?category=catalog'):
                    response = client.get('/api/v1/products/catalog/' + query)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.data['count'], 0)
                self.assertEqual(client.get(f'/api/v1/products/catalog/{self.product.slug}/').status_code, 404)
                self.assertEqual(client.get(f'/api/v1/products/catalog/by-id/{self.product.pk}/').status_code, 404)

    def test_workspace_and_preview_require_inventory_permission(self):
        for user, allowed in ((None, False), (self.customer, False), (self.staff, True), (self.superuser, True)):
            client = APIClient()
            client.force_authenticate(user)
            workspace = client.get('/api/v1/products/catalog/?workspace=admin')
            preview = client.get(f'/api/v1/products/catalog/{self.product.slug}/preview/')
            if allowed:
                self.assertEqual(workspace.status_code, 200)
                self.assertEqual(workspace.data['count'], 1)
                self.assertEqual(preview.status_code, 200)
                self.assertIn('no-store', preview['Cache-Control'])
            else:
                self.assertIn(workspace.status_code, (401, 403))
                self.assertIn(preview.status_code, (401, 403))

    def test_publish_unpublish_and_category_deactivation(self):
        client = APIClient()
        client.force_authenticate(self.staff)
        url = f'/api/v1/products/catalog/{self.product.slug}/'
        self.assertEqual(client.patch(url, {'status': 'published'}, format='json').status_code, 200)
        self.assertEqual(client.get(url).status_code, 200)
        self.assertEqual(client.patch(url, {'status': 'draft'}, format='json').status_code, 200)
        self.assertEqual(client.get(url).status_code, 404)
        Product.objects.filter(pk=self.product.pk).update(status='published')
        Category.objects.filter(pk=self.product.category_id).update(is_active=False)
        self.assertEqual(client.get(url).status_code, 404)

    def test_public_category_counts_exclude_drafts_for_staff(self):
        client = APIClient()
        client.force_authenticate(self.staff)
        public = client.get('/api/v1/products/categories/')
        workspace = client.get('/api/v1/products/categories/?workspace=admin')
        self.assertEqual(public.data['results'][0]['product_count'], 0)
        self.assertEqual(workspace.data['results'][0]['product_count'], 1)
