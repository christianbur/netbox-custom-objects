"""Set every Bundle activation record to disabled (opt-in activation)."""

from django.core.management.base import BaseCommand

from netbox_custom_objects.models import Bundle


class Command(BaseCommand):
    help = (
        "Set enabled=False on all Bundle records.  Use after importing bundles "
        "or when resetting a dev environment; restart NetBox workers afterward."
    )

    def handle(self, *args, **options):
        updated = Bundle.objects.filter(enabled=True).update(enabled=False)
        self.stdout.write(
            self.style.SUCCESS(
                f"Disabled {updated} bundle(s). Restart NetBox workers to apply."
            )
        )
