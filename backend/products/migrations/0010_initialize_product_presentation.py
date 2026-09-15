from django.db import migrations


def initialize(apps, schema_editor):
    Product = apps.get_model('products', 'Product')
    Specification = apps.get_model('products', 'ProductSpecification')
    for product in Product.objects.using(schema_editor.connection.alias).select_related('category').iterator():
        slug = product.category.slug.lower()
        layout = 'license' if product.licensing_role == 'license_product' else 'radio' if 'radio' in slug and 'holster' not in slug else 'accessory'
        Product.objects.using(schema_editor.connection.alias).filter(pk=product.pk).update(detail_layout=layout)
        if layout == 'radio':
            ids = list(Specification.objects.using(schema_editor.connection.alias).filter(product_id=product.pk).order_by('sort_order', 'id').values_list('pk', flat=True)[:4])
            Specification.objects.using(schema_editor.connection.alias).filter(pk__in=ids).update(show_in_highlights=True)


class Migration(migrations.Migration):
    dependencies = [('products', '0009_product_detail_layout_product_presentation_overrides_and_more')]
    operations = [migrations.RunPython(initialize, migrations.RunPython.noop)]
