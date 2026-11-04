import { useQueryClient } from "@tanstack/react-query";
import QRCode from "qrcode";
import { useEffect, useState } from "react";

import { api, ApiError } from "@/api/client";
import { keys } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input } from "@/components/ui/field";

import { FormError } from "./AuthCard";

interface Setup {
  secret: string;
  otpauth_uri: string;
  setup_token: string;
}

/** QR + manual secret → verify a code → recovery codes shown once (docs/07 §5.1). */
export function MfaEnrollment({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient();
  const [setup, setSetup] = useState<Setup | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const run = { cancelled: false };
    void (async () => {
      try {
        const { data } = await api.POST("/api/v1/auth/mfa/setup");
        if (!data || run.cancelled) return;
        setSetup(data);
        setQr(await QRCode.toDataURL(data.otpauth_uri, { margin: 1, width: 180 }));
      } catch (e) {
        if (!run.cancelled)
          setError(e instanceof ApiError ? (e.detail ?? e.code) : "Could not start the setup.");
      }
    })();
    return () => {
      run.cancelled = true;
    };
  }, []);

  async function enable() {
    if (!setup) return;
    setError(null);
    try {
      const { data } = await api.POST("/api/v1/auth/mfa/enable", {
        body: { setup_token: setup.setup_token, code },
      });
      setCodes(data?.recovery_codes ?? []);
      await qc.invalidateQueries({ queryKey: keys.me });
    } catch (e) {
      setError(e instanceof ApiError ? (e.detail ?? e.code) : "The code is not valid.");
      setCode("");
    }
  }

  function download() {
    if (!codes) return;
    const blob = new Blob([codes.join("\n") + "\n"], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "recovery-codes.txt";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  if (codes) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm text-ink-secondary">
          Save these recovery codes. Each works once if you lose access to your authenticator. They are shown
          only now.
        </p>
        <ul
          aria-label="Recovery codes"
          className="grid grid-cols-2 gap-2 rounded-control border border-border bg-ground p-3 font-mono text-sm"
        >
          {codes.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
        <Button variant="secondary" onClick={download}>
          Download codes
        </Button>
        <Checkbox
          label="I've saved these codes"
          checked={saved}
          onChange={(e) => {
            setSaved(e.target.checked);
          }}
        />
        <Button disabled={!saved} onClick={onDone}>
          Continue
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <FormError message={error} />
      {setup ? (
        <>
          <p className="text-sm text-ink-secondary">
            Scan the QR code with an authenticator app, or enter the key manually.
          </p>
          {qr ? (
            <img src={qr} alt="QR code for your authenticator app" className="mx-auto size-[180px]" />
          ) : null}
          <p
            className="break-all rounded-control bg-ground p-2 text-center font-mono text-sm"
            aria-label="Manual setup key"
          >
            {setup.secret}
          </p>
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              void enable();
            }}
          >
            <Field label="Verification code">
              {(p) => (
                <Input
                  {...p}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  className="font-mono tracking-widest"
                  value={code}
                  onChange={(e) => {
                    setCode(e.target.value.replace(/\D/g, ""));
                  }}
                />
              )}
            </Field>
            <Button type="submit" disabled={code.length !== 6}>
              Verify and enable
            </Button>
          </form>
        </>
      ) : null}
    </div>
  );
}
