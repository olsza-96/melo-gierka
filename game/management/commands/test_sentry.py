from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

import sentry_sdk


class Command(BaseCommand):
    help = "Send a one-time Sentry smoke-test event from this app."

    def add_arguments(self, parser):
        parser.add_argument(
            "--message",
            default="Sentry smoke test from melo-gierka",
            help="Message sent to Sentry.",
        )
        parser.add_argument(
            "--level",
            choices=["debug", "info", "warning", "error", "fatal"],
            default="warning",
            help="Event level for the test message.",
        )
        parser.add_argument(
            "--with-exception",
            action="store_true",
            help="Also send a captured RuntimeError as a test exception.",
        )

    def handle(self, *args, **options):
        sentry_dsn = (getattr(settings, "SENTRY_DSN", "") or "").strip()
        if not sentry_dsn:
            raise CommandError(
                "SENTRY_DSN is empty. Set it in environment first, then run this command."
            )

        message = options["message"]
        level = options["level"]

        msg_event_id = sentry_sdk.capture_message(message, level=level)
        self.stdout.write(
            self.style.SUCCESS(
                f"Sentry message event sent (event_id={msg_event_id or 'n/a'})."
            )
        )

        if options["with_exception"]:
            try:
                raise RuntimeError(message)
            except RuntimeError as exc:
                exc_event_id = sentry_sdk.capture_exception(exc)
                self.stdout.write(
                    self.style.SUCCESS(
                        "Sentry exception event sent "
                        f"(event_id={exc_event_id or 'n/a'})."
                    )
                )

        sentry_sdk.flush(timeout=2.0)
        self.stdout.write(self.style.SUCCESS("Sentry flush finished."))
