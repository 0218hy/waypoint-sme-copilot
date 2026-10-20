import {
  AlertTriangle,
  ArrowDown,
  MessageSquareWarning,
  RotateCw,
} from "lucide-react";
import { domAnimation, LazyMotion, useReducedMotion } from "motion/react";
import * as m from "motion/react-m";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MutableRefObject,
} from "react";
import { useTranslation } from "react-i18next";
import { DemoControls } from "@/components/DemoControls";
import { Button } from "@/components/ui/button";
import type { JourneyStep } from "@/lib/api";
import { LG, useMediaQuery, XL } from "@/lib/useMediaQuery";
import type { Emit } from "@/widgets/types";
import { WidgetView } from "@/widgets/WidgetView";
import { Canvas } from "./Canvas";
import { RATE_LIMITED, useChat, type ChatNotice } from "./chatContext";
import { Composer } from "./Composer";
import { HeroReference } from "./HeroReference";
import { PlanSoFar } from "./PlanSoFar";
import { ProgressStrip } from "./ProgressStrip";
import { StepRail } from "./StepRail";
import { HERO_TYPES, useTranscript, type Transcript } from "./transcript";

export function ChatTab({ demo = false }: { demo?: boolean }) {
  const { t } = useTranslation();
  const chat = useChat();
  const { messages, journey, running } = chat;
  const transcript = useTranscript(messages, journey);
  const wide = useMediaQuery(LG);
  const canvasOn = useMediaQuery(XL);

  // The canvas follows the newest hero widget unless the owner picked an older one since it arrived.
  const [pinned, setPinned] = useState<{
    key: string;
    latest: string | undefined;
  } | null>(null);
  const latestKey = transcript.latestHero?.key;
  const canvasKey =
    pinned && pinned.latest === latestKey && transcript.byKey.has(pinned.key)
      ? pinned.key
      : latestKey;
  const canvasEntry = canvasKey ? transcript.byKey.get(canvasKey) : undefined;
  const showInCanvas = (key: string) => setPinned({ key, latest: latestKey });

  const emitFor =
    (widgetId: string): Emit =>
    (event, { value, data, label }) =>
      chat.sendEvent(
        { widget_id: widgetId, event, value: value ?? null, data: data ?? {} },
        label,
      );

  // A message typed in the composer always brings the view down to the reply.
  const followNextRef = useRef(false);
  const send = (text: string) => {
    followNextRef.current = true;
    return chat.sendText(text);
  };

  const reopen = (s: JourneyStep) =>
    chat.sendEvent(
      {
        widget_id: "progress_strip",
        event: "reopen_step",
        value: s.id,
        data: { step: s.id },
      },
      t("chat.reopenLabel", { step: s.label }),
    );
  const steps = journey?.steps ?? [];

  const chatColumn = (
    <div className="flex min-h-0 flex-1 flex-col">
      {!wide && steps.length > 0 && (
        <ProgressStrip steps={steps} disabled={running} onReopen={reopen} />
      )}
      <MessageList
        transcript={transcript}
        heroInCanvas={canvasOn}
        canvasKey={canvasKey}
        onShowInCanvas={showInCanvas}
        emitFor={emitFor}
        followNextRef={followNextRef}
      />
      <Composer onSend={send} busy={running} />
    </div>
  );

  if (!wide) return chatColumn;

  return (
    <div className="grid min-h-0 flex-1 grid-cols-[264px_minmax(0,1fr)] xl:grid-cols-[248px_minmax(420px,1fr)_minmax(480px,1.15fr)]">
      <aside
        aria-label={t("chat.rail")}
        className="flex min-h-0 flex-col gap-5 overflow-y-auto border-r border-border bg-surface/50 px-3 py-4"
      >
        <StepRail steps={steps} disabled={running} onReopen={reopen} />
        <PlanSoFar entries={transcript.entries} />
        {demo && <DemoControls compact />}
      </aside>
      <div className="flex min-h-0 flex-col">{chatColumn}</div>
      {canvasOn && (
        <Canvas
          entry={canvasEntry}
          isLatest={canvasKey === latestKey}
          disabled={
            (canvasEntry
              ? (transcript.supersededById.get(canvasEntry.key) ?? false)
              : false) || running
          }
          busy={
            !!canvasEntry?.widget &&
            journey?.busy_widget === canvasEntry.widget.id
          }
          emit={emitFor(canvasEntry?.widget?.id ?? canvasKey ?? "")}
          onRetry={chat.retry}
          onShowLatest={() => setPinned(null)}
        />
      )}
    </div>
  );
}

function MessageList({
  transcript,
  heroInCanvas,
  canvasKey,
  onShowInCanvas,
  emitFor,
  followNextRef,
}: {
  transcript: Transcript;
  heroInCanvas: boolean;
  canvasKey: string | undefined;
  onShowInCanvas: (key: string) => void;
  emitFor: (widgetId: string) => Emit;
  followNextRef: MutableRefObject<boolean>;
}) {
  const { t } = useTranslation();
  const chat = useChat();
  const { messages, journey, running, error, notice, thinking, slots } = chat;
  const reduced = useReducedMotion();
  const scrollRef = useRef<HTMLDivElement>(null);
  // Whether the owner is reading at the bottom, and whether we follow the current turn.
  const atBottom = useRef(true);
  const follow = useRef(true);
  const autoUntil = useRef(0);
  const turnUser = useRef<string | undefined>(undefined);
  const shown = useRef(false);
  const [unseen, setUnseen] = useState(false);

  // Scroll only the message pane (scrollIntoView would also scroll the page in a WebView).
  const scrollPane = useCallback(
    (top: number, smooth: boolean) => {
      const box = scrollRef.current;
      if (!box) return;
      autoUntil.current = Date.now() + (smooth && !reduced ? 600 : 80);
      box.scrollTo({ top, behavior: smooth && !reduced ? "smooth" : "auto" });
    },
    [reduced],
  );
  const toLatest = () => {
    const box = scrollRef.current;
    if (!box) return;
    follow.current = true;
    setUnseen(false);
    scrollPane(box.scrollHeight, true);
  };

  // Follow the conversation only while the owner is with it. A turn is followed when it starts with the
  // owner at the bottom (a reply, a quick reply, a typed message); tapping a card further up leaves the
  // view where it is and offers a "new messages" button instead. While a reply streams in, the view keeps up
  // only until the reply's start would scroll out of sight, so a tall card is read from its top. Scrolling
  // up by hand stops the following at once.
  const lastUser = [...messages].reverse().find((msg) => msg.role === "user");
  useEffect(() => {
    const box = scrollRef.current;
    if (!box || messages.length === 0) return;
    if (!shown.current) {
      // Opening the chat: start at the latest message.
      shown.current = true;
      turnUser.current = lastUser?.id;
      scrollPane(box.scrollHeight, false);
      return;
    }
    if (lastUser?.id !== turnUser.current) {
      turnUser.current = lastUser?.id;
      follow.current = atBottom.current || followNextRef.current;
      followNextRef.current = false;
    }
    if (!follow.current) {
      if (!atBottom.current) setUnseen(true);
      return;
    }
    const start = lastUser
      ? messages.findIndex((msg) => msg.id === lastUser.id)
      : -1;
    const reply = messages
      .slice(start + 1)
      .find((msg) => msg.role === "assistant");
    const el = reply ? document.getElementById(`msg-${reply.id}`) : null;
    const replyTop = el
      ? el.getBoundingClientRect().top -
        box.getBoundingClientRect().top +
        box.scrollTop -
        12
      : null;
    const bottom = box.scrollHeight - box.clientHeight;
    if (replyTop !== null && replyTop < bottom) {
      // The reply is taller than the view: show it from its start, then let the owner read.
      scrollPane(replyTop, true);
      follow.current = false;
      return;
    }
    scrollPane(box.scrollHeight, false);
  }, [messages, running, error, notice, lastUser, followNextRef, scrollPane]);

  const visible = messages.filter(
    (msg) => msg.role === "user" || msg.role === "assistant",
  );
  const last = visible[visible.length - 1];
  const streamingText =
    running &&
    last?.role === "assistant" &&
    typeof last.content === "string" &&
    last.content.length > 0;

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div
        ref={scrollRef}
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain"
        onScroll={(e) => {
          const el = e.currentTarget;
          atBottom.current =
            el.scrollHeight - el.scrollTop - el.clientHeight < 120;
          if (atBottom.current) setUnseen(false);
          // The owner scrolled up by hand: stop following this turn.
          if (Date.now() >= autoUntil.current && !atBottom.current)
            follow.current = false;
        }}
      >
        <LazyMotion features={domAnimation}>
          <div
            role="log"
            aria-live="polite"
            aria-relevant="additions"
            aria-label={t("chat.log")}
            className="mx-auto flex max-w-2xl flex-col gap-3 px-3 py-4 lg:max-w-[720px] lg:px-6"
          >
            {visible.length === 0 && !running && !error && (
              <p className="py-10 text-center text-sm text-muted">
                {t("chat.empty")}
              </p>
            )}
            {visible.map((msg) => {
              if (msg.role === "user") {
                const text = typeof msg.content === "string" ? msg.content : "";
                if (!text) return null;
                return (
                  <m.div
                    key={msg.id}
                    initial={reduced ? false : { opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.18 }}
                    className="ml-10 self-end rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-[15px] whitespace-pre-line text-accent-fg"
                  >
                    <span className="sr-only">{t("chat.you")}: </span>
                    {text}
                  </m.div>
                );
              }
              if (msg.role !== "assistant") return null;
              const text = typeof msg.content === "string" ? msg.content : "";
              return (
                <m.div
                  key={msg.id}
                  id={`msg-${msg.id}`}
                  initial={reduced ? false : { opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.18 }}
                  className="flex scroll-mt-3 flex-col gap-3"
                >
                  {!text && slots.has(msg.id) && (
                    <TypingIndicator stage={thinking} />
                  )}
                  {text && (
                    <div className="mr-8 self-start rounded-2xl rounded-bl-md border border-border bg-surface px-4 py-2.5 text-[15px] whitespace-pre-line shadow-card">
                      <span className="sr-only">{t("chat.bot")}: </span>
                      {text}
                    </div>
                  )}
                  {msg.toolCalls?.map((tc) => {
                    const entry = transcript.byKey.get(tc.id);
                    const widget = entry?.widget ?? null;
                    const superseded =
                      transcript.supersededById.get(tc.id) ?? false;
                    if (
                      heroInCanvas &&
                      widget &&
                      HERO_TYPES.has(tc.function.name)
                    ) {
                      return (
                        <HeroReference
                          key={tc.id}
                          widget={widget}
                          shown={canvasKey === tc.id}
                          replaced={transcript.replacedById.get(tc.id) ?? false}
                          onShow={() => onShowInCanvas(tc.id)}
                        />
                      );
                    }
                    return (
                      <div key={tc.id} className="w-full">
                        <WidgetView
                          name={tc.function.name}
                          widget={widget}
                          complete={
                            !running ||
                            messages.indexOf(msg) < messages.length - 1
                          }
                          emit={emitFor(widget?.id ?? tc.id)}
                          disabled={superseded || running}
                          busy={!!widget && journey?.busy_widget === widget.id}
                          onRetry={chat.retry}
                        />
                      </div>
                    );
                  })}
                </m.div>
              );
            })}
            {running && !streamingText && slots.size === 0 && (
              <TypingIndicator stage={thinking} />
            )}
            {notice && !running && (
              <NoticeCard notice={notice} onRetry={chat.retryCompose} />
            )}
            {error && !running && (
              <div
                role="alert"
                className="flex flex-col items-start gap-2 self-start rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger"
              >
                <p className="inline-flex items-center gap-2 font-medium">
                  <AlertTriangle aria-hidden className="size-4" />
                  {error === RATE_LIMITED
                    ? t("chat.rateLimited")
                    : t("chat.error")}
                </p>
                <Button size="sm" variant="secondary" onClick={chat.retry}>
                  <RotateCw aria-hidden />
                  {t("common.retry")}
                </Button>
              </div>
            )}
          </div>
        </LazyMotion>
      </div>
      {unseen && (
        <Button
          size="sm"
          variant="secondary"
          onClick={toLatest}
          className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full shadow-card"
        >
          <ArrowDown aria-hidden />
          {t("chat.newMessages")}
        </Button>
      )}
    </div>
  );
}

const NOTICE_TEXT: Record<
  string,
  | "chat.notice.unavailable"
  | "chat.notice.linkInvalid"
  | "chat.notice.checkinRecorded"
  | "chat.notice.checkinAlready"
> = {
  model_unavailable: "chat.notice.unavailable",
  link_invalid: "chat.notice.linkInvalid", // an email link the server refused (expired, tampered, not this goal)
  checkin_recorded: "chat.notice.checkinRecorded",
  checkin_already: "chat.notice.checkinAlready",
};

/** `waypoint.notice`: the model couldn't word this turn (the cards are current), or a plain notice. */
function NoticeCard({
  notice,
  onRetry,
}: {
  notice: ChatNotice;
  onRetry: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      className="flex items-start gap-2 self-start rounded-2xl border border-border bg-surface-2 px-3 py-2 text-sm text-muted"
    >
      <MessageSquareWarning aria-hidden className="mt-0.5 size-4 shrink-0" />
      <p className="flex-1">
        {t(NOTICE_TEXT[notice.code] ?? "chat.notice.composeFailed")}
      </p>
      {notice.retry && (
        <Button
          size="sm"
          variant="link"
          className="min-h-0 text-sm"
          onClick={onRetry}
        >
          {t("common.retry")}
        </Button>
      )}
    </div>
  );
}

const STAGES = ["reading", "computing", "composing"] as const;

function TypingIndicator({ stage }: { stage: string | null }) {
  const { t } = useTranslation();
  const known = STAGES.find((s) => stage?.startsWith(s.slice(0, 4)));
  const hint = stage
    ? known
      ? t(`chat.thinking.${known}`)
      : t("chat.thinking.generic")
    : null;
  return (
    <div
      role="status"
      className="inline-flex items-center gap-2 self-start rounded-2xl rounded-bl-md border border-border bg-surface px-4 py-3"
    >
      <span className="sr-only">{hint ?? t("chat.typing")}</span>
      <span className="inline-flex gap-1" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="wp-dot size-2 rounded-full bg-faint"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </span>
      {hint && (
        <span aria-hidden className="text-xs text-muted">
          {hint}
        </span>
      )}
    </div>
  );
}
