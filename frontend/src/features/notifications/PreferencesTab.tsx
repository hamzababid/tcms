/** Your account › Notifications (US-171, AC-NTF-02/03): opt out of mention emails and the digest. */
import { useState } from "react";

import { errorMessage, ErrorState, Skeleton, useToast } from "@/components/common/feedback";
import { ToggleField } from "@/components/ui/field";

import {
  saveEmailPreferences,
  useEmailPreferences,
  useInvalidateNotifications,
  type EmailPreferences,
} from "./api";

export function NotificationPreferencesTab() {
  const prefs = useEmailPreferences();
  if (prefs.isPending) return <Skeleton />;
  if (prefs.isError) return <ErrorState error={prefs.error} />;
  return <Preferences initial={prefs.data} />;
}

function Preferences({ initial }: { initial: EmailPreferences }) {
  const [value, setValue] = useState(initial);
  const invalidate = useInvalidateNotifications();
  const toast = useToast();
  const save = (patch: Partial<EmailPreferences>) => {
    const previous = value;
    setValue({ ...value, ...patch });
    saveEmailPreferences(patch)
      .then((saved) => {
        setValue(saved);
        invalidate();
        toast("Email settings saved");
      })
      .catch((err: unknown) => {
        setValue(previous);
        toast(errorMessage(err), "error");
      });
  };
  return (
    <div className="flex max-w-xl flex-col gap-5">
      <p className="text-[13px] text-ink-secondary">
        In-app notifications in the bell are always on. Choose which ones also reach you by email.
      </p>
      <ToggleField
        label="Email me when someone mentions me"
        description="Sent right away, with a link to the comment."
        checked={value.mentions}
        onChange={(e) => {
          save({ mentions: e.target.checked });
        }}
      />
      <ToggleField
        label="Daily summary of runs assigned to me"
        description="Sent at 07:00 in your time zone when new runs were assigned to you."
        checked={value.digest}
        onChange={(e) => {
          save({ digest: e.target.checked });
        }}
      />
    </div>
  );
}
