"use client";

import { useRef, useState } from "react";
import { apiPatch } from "@/lib/api";
import { createClient } from "@/lib/supabase";
import type { Me } from "@/lib/useMe";
import { Avatar } from "./Avatar";
import { Button, ErrorText, inputCls } from "./ui";

const MAX_BYTES = 2 * 1024 * 1024; // 2 MB
const TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];

// Saves only the photo. Sends the other fields unchanged, so PATCH /me
// works whether or not your schema makes them optional.
async function saveAvatar(me: Me, avatar_url: string) {
  await apiPatch("/me", {
    name: me.name,
    paypal_email: me.paypal_email,
    skills: me.skills,
    hourly_rate_cents: me.hourly_rate_cents,
    available: me.available,
    avatar_url,
  });
}

export function AvatarPicker({ me, onSaved }: { me: Me; onSaved: () => Promise<unknown> | void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<"upload" | "url" | "remove" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showUrl, setShowUrl] = useState(false);
  const [url, setUrl] = useState("");

  async function run(kind: "upload" | "url" | "remove", fn: () => Promise<void>) {
    setBusy(kind);
    setErr(null);
    try {
      await fn();
      await onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't update your photo");
    } finally {
      setBusy(null);
    }
  }

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // let the same file be picked again
    if (!file) return;
    if (!TYPES.includes(file.type)) return setErr("Use a JPG, PNG, WebP, or GIF image.");
    if (file.size > MAX_BYTES) return setErr("That image is over 2 MB. Pick a smaller one.");

    run("upload", async () => {
      const supabase = createClient();
      const { data: auth } = await supabase.auth.getUser();
      if (!auth.user) throw new Error("Sign in again to upload a photo.");
      const ext = file.name.split(".").pop()?.toLowerCase() || "png";
      // One folder per user. The storage policy only lets you write to your own folder.
      const path = `${auth.user.id}/avatar-${Date.now()}.${ext}`;
      const { error } = await supabase.storage
        .from("avatars")
        .upload(path, file, { contentType: file.type, upsert: false });
      if (error) throw new Error(`Upload failed: ${error.message}`);
      const { data } = supabase.storage.from("avatars").getPublicUrl(path);
      await saveAvatar(me, data.publicUrl);
    });
  }

  function onUrl(e: React.FormEvent) {
    e.preventDefault();
    const clean = url.trim();
    if (!/^https:\/\/\S+$/i.test(clean)) return setErr("Paste a link that starts with https://");
    run("url", async () => {
      await saveAvatar(me, clean);
      setUrl("");
      setShowUrl(false);
    });
  }

  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
      <Avatar name={me.name} url={me.avatar_url} size={80} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">Profile photo</p>
        <p className="text-xs text-muted">Shown in the menu and next to your name. JPG, PNG, or WebP, up to 2 MB.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <input ref={fileRef} type="file" accept={TYPES.join(",")} className="hidden" onChange={onFile} />
          <Button type="button" variant="quiet" disabled={!!busy} onClick={() => fileRef.current?.click()}>
            {busy === "upload" ? "Uploading…" : "Upload photo"}
          </Button>
          <Button type="button" variant="quiet" disabled={!!busy} onClick={() => setShowUrl((s) => !s)}>
            Use a link
          </Button>
          {me.avatar_url && (
            <Button
              type="button"
              variant="danger"
              disabled={!!busy}
              onClick={() => run("remove", () => saveAvatar(me, ""))}
            >
              {busy === "remove" ? "Removing…" : "Remove"}
            </Button>
          )}
        </div>
        {showUrl && (
          <form onSubmit={onUrl} className="mt-3 flex flex-col gap-2 sm:flex-row">
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/me.jpg"
              className={inputCls}
              autoFocus
            />
            <Button disabled={!!busy || !url.trim()} className="shrink-0">
              {busy === "url" ? "Saving…" : "Save link"}
            </Button>
          </form>
        )}
        <ErrorText>{err}</ErrorText>
      </div>
    </div>
  );
}
