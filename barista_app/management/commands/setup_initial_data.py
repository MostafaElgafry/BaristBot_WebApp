"""
Management command to set up initial data for the Barista Robot Control System.
"""
from django.core.management.base import BaseCommand
from barista_app.models import (
    UserProfile, CoffeeType, Grinder, Dozer, Recipe,
    ToneMachineButton, Inventory, SystemSettings
)


class Command(BaseCommand):
    help = 'Set up initial data for the Barista Robot Control System'

    def handle(self, *args, **options):
        self.stdout.write('Setting up initial data...')

        # Create coffee types
        coffee_types = [
            {'name': 'Ethiopian Yirgacheffe', 'origin': 'Ethiopia', 'description': 'Fruity and floral notes'},
            {'name': 'Colombian Supremo', 'origin': 'Colombia', 'description': 'Balanced with nutty undertones'},
            {'name': 'Exotic Blend', 'origin': 'Various', 'description': 'House special blend'},
            {'name': 'Indonesian Sumatra', 'origin': 'Indonesia', 'description': 'Earthy and full-bodied'},
        ]

        for ct_data in coffee_types:
            ct, created = CoffeeType.objects.get_or_create(name=ct_data['name'], defaults=ct_data)
            if created:
                self.stdout.write(f'  Created coffee type: {ct.name}')

        # Create recipes
        recipes = [
            {'name': 'Espresso', 'description': 'Classic single shot'},
            {'name': 'Double Espresso', 'description': 'Double shot'},
            {'name': 'Americano', 'description': 'Espresso with hot water'},
            {'name': 'Lungo', 'description': 'Long espresso'},
        ]

        for r_data in recipes:
            recipe, created = Recipe.objects.get_or_create(name=r_data['name'], defaults=r_data)
            if created:
                self.stdout.write(f'  Created recipe: {recipe.name}')

        # Create tone machine buttons
        for i in range(1, 5):
            recipe = Recipe.objects.filter(is_active=True).first()
            btn, created = ToneMachineButton.objects.get_or_create(
                button_number=i,
                defaults={
                    'recipe': recipe if i <= Recipe.objects.count() else None,
                    'label': f'Recipe {i}'
                }
            )
            if created:
                self.stdout.write(f'  Created tone button: {i}')

        # Create default grinder
        coffee_type = CoffeeType.objects.first()
        grinder, created = Grinder.objects.get_or_create(
            name='Main Grinder',
            defaults={
                'coffee_type': coffee_type,
                'grind_level': 5
            }
        )
        if created:
            self.stdout.write('  Created default grinder')

        # Create default dozer
        dozer, created = Dozer.objects.get_or_create(
            name='Main Dozer',
            defaults={
                'dose_grams': 18.0,
                'linked_grinder': grinder
            }
        )
        if created:
            self.stdout.write('  Created default dozer')

        # Create inventory items
        inventory_items = [
            {'item_type': 'bean', 'name': 'Ethiopian Beans', 'current_level': 75, 'coffee_type': CoffeeType.objects.filter(name__icontains='Ethiopian').first()},
            {'item_type': 'bean', 'name': 'Colombian Beans', 'current_level': 45, 'coffee_type': CoffeeType.objects.filter(name__icontains='Colombian').first()},
            {'item_type': 'bean', 'name': 'Exotic Blend Beans', 'current_level': 20, 'coffee_type': CoffeeType.objects.filter(name__icontains='Exotic').first()},
            {'item_type': 'bean', 'name': 'Indonesian Beans', 'current_level': 90, 'coffee_type': CoffeeType.objects.filter(name__icontains='Indonesian').first()},
            {'item_type': 'cup_takeaway', 'name': 'Takeaway Cups', 'current_count': 150, 'current_level': 75},
            {'item_type': 'cup_dinein', 'name': 'Dine-in Cups', 'current_count': 50, 'current_level': 50},
            {'item_type': 'server', 'name': 'Servers', 'current_count': 20, 'current_level': 100},
        ]

        for inv_data in inventory_items:
            inv, created = Inventory.objects.get_or_create(
                name=inv_data['name'],
                defaults=inv_data
            )
            if created:
                self.stdout.write(f'  Created inventory: {inv.name}')

        # Create system settings
        SystemSettings.get_settings()
        self.stdout.write('  Initialized system settings')

        # Create default admin user if not exists
        if not UserProfile.objects.filter(username='admin').exists():
            admin = UserProfile.objects.create_superuser(
                username='admin',
                email='admin@barista.local',
                password='admin123',
                role='manager'
            )
            self.stdout.write(self.style.SUCCESS(f'  Created admin user (password: admin123)'))

        # Create sample users
        sample_users = [
            {'username': 'barista1', 'password': 'barista123', 'role': 'barista'},
            {'username': 'tech1', 'password': 'tech123', 'role': 'technician'},
            {'username': 'supervisor1', 'password': 'super123', 'role': 'supervisor'},
        ]

        for u_data in sample_users:
            if not UserProfile.objects.filter(username=u_data['username']).exists():
                user = UserProfile.objects.create_user(
                    username=u_data['username'],
                    password=u_data['password'],
                    role=u_data['role']
                )
                self.stdout.write(f'  Created user: {u_data["username"]} (password: {u_data["password"]})')

        self.stdout.write(self.style.SUCCESS('Initial data setup complete!'))
