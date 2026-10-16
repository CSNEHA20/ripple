import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, Link2, X, Bot, User, Clock } from 'lucide-react';
import type { AskBrainResponse } from '../api';

interface AskBrainDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onAsk: (question: string) => Promise<AskBrainResponse>;
  onSelectNodeId?: (nodeId: string) => void;
}

export const AskBrainDrawer: React.FC<AskBrainDrawerProps> = ({ isOpen, onClose, onAsk, onSelectNodeId }) => {
  const [question, setQuestion] = useState('');
  const [pending, setPending] = useState<string | null>(null);
  const [history, setHistory] = useState<AskBrainResponse[]>([]);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [history, pending]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleSend = async (qToSend?: string) => {
    const q = (qToSend || question).trim();
    if (!q || pending) return;
    setPending(q);
    setQuestion('');
    try {
      const resp = await onAsk(q);
      setHistory((prev) => [...prev, resp]);
    } catch (err) {
      console.error(err);
      setHistory((prev) => [...prev, { question: q, answer: 'Sorry — I could not reach the graph right now. Please try again.', intent: 'error', sources: [] }]);
    } finally {
      setPending(null);
    }
  };

  const sampleQuestions = [
    'Who owns the payment service and who actually knows it?',
    'Why did we choose gRPC for checkout communication?',
    'What breaks if currency service goes down?',
    'Which docs describing checkout might be out of date?',
  ];

  return (
    <div className="overlay flex justify-end" onClick={onClose}>
      <div className="drawer w-[560px] max-w-[94vw] h-full flex flex-col" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="relative px-6 py-5 border-b border-[var(--border-default)] overflow-hidden">
          <div className="absolute -top-16 -right-10 w-48 h-48 bg-[#ff4d2d]/25 rounded-full blur-3xl pointer-events-none" />
          <div className="relative flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="w-10 h-10 rounded-2xl grid place-items-center bg-gradient-to-br from-[#ff4d2d] to-[#f97316] text-white shadow-[0_8px_24px_-6px_rgba(255,77,45,0.8)]">
                <Sparkles size={18} />
              </span>
              <div>
                <h3 className="font-bold text-[16px] tracking-tight text-[var(--text-primary)] leading-none">Ask Company Brain</h3>
                <p className="text-[12px] text-[var(--text-muted)] mt-1.5">Answers grounded in graph facts, with citations</p>
              </div>
            </div>
            <button className="icon-btn" onClick={onClose}><X size={17} /></button>
          </div>
        </div>

        {/* Conversation */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {history.length === 0 && !pending ? (
            <div className="pt-6 space-y-6 anim-fade-up">
              <div className="text-center">
                <div className="w-16 h-16 rounded-3xl mx-auto mb-4 grid place-items-center bg-[#ff4d2d]/10 text-[#ff4d2d] border border-[#ff4d2d]/25">
                  <Bot size={28} />
                </div>
                <h4 className="text-[17px] font-bold text-[var(--text-primary)]">What would you like to know?</h4>
                <p className="text-[13px] text-[var(--text-muted)] mt-1.5 max-w-xs mx-auto leading-relaxed">
                  Ask about architecture, ownership, decisions, or incidents. Every claim links back to the graph.
                </p>
              </div>
              <div className="space-y-2">
                {sampleQuestions.map((sq, i) => (
                  <button
                    key={i}
                    onClick={() => handleSend(sq)}
                    className="w-full text-left p-3.5 rounded-2xl border border-[var(--border-default)] bg-[var(--bg-inset)]/60 hover:border-[#ff4d2d]/50 hover:bg-[var(--bg-tertiary)] hover:-translate-y-0.5 transition-all text-[13px] font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] anim-fade-up"
                    style={{ ['--i' as string]: i + 1 }}
                  >
                    {sq}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              {history.map((item, idx) => (
                <div key={idx} className="space-y-3 anim-fade-up">
                  <div className="flex justify-end gap-2.5">
                    <div className="max-w-[85%] px-4 py-2.5 rounded-2xl rounded-tr-md bg-gradient-to-br from-[#ff4d2d] to-[#f97316] text-white text-[13.5px] font-medium shadow-lg">
                      {item.question}
                    </div>
                    <span className="w-7 h-7 rounded-full bg-[var(--bg-tertiary)] border border-[var(--border-default)] grid place-items-center shrink-0 text-[var(--text-muted)]"><User size={13} /></span>
                  </div>

                  <div className="flex gap-2.5">
                    <span className="w-7 h-7 rounded-full bg-[#ff4d2d]/15 border border-[#ff4d2d]/30 grid place-items-center shrink-0 text-[#ff4d2d]"><Sparkles size={13} /></span>
                    <div className="flex-1 min-w-0 space-y-3">
                      <div className="surface !rounded-2xl !rounded-tl-md p-4 text-[13.5px] leading-relaxed text-[var(--text-primary)] whitespace-pre-wrap">
                        {item.answer}
                      </div>
                      {item.intent && item.intent !== 'error' && (
                        <span className="chip chip-mono !text-[10.5px]"><Clock size={10} /> intent: {item.intent}</span>
                      )}
                      {item.sources && item.sources.length > 0 && (
                        <div>
                          <div className="flex items-center gap-1.5 eyebrow mb-2"><Link2 size={11} /> Graph citations</div>
                          <div className="flex flex-wrap gap-1.5">
                            {item.sources.map((src, sIdx) => (
                              <button
                                key={sIdx}
                                onClick={() => onSelectNodeId?.(src.id)}
                                title="Locate node on graph"
                                className={`chip chip-mono !text-[10.5px] cursor-pointer hover:-translate-y-0.5 transition-transform ${src.stale ? 'chip-amber' : src.superseded ? 'chip-red' : 'chip-cyan'}`}
                              >
                                {src.title || src.id}
                                {src.stale && <b>STALE</b>}
                                {src.superseded && <b>SUPERSEDED</b>}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}

              {pending && (
                <div className="space-y-3 anim-fade-up">
                  <div className="flex justify-end">
                    <div className="max-w-[85%] px-4 py-2.5 rounded-2xl rounded-tr-md bg-gradient-to-br from-[#ff4d2d] to-[#f97316] text-white text-[13.5px] font-medium">{pending}</div>
                  </div>
                  <div className="flex gap-2.5 items-center">
                    <span className="w-7 h-7 rounded-full bg-[#ff4d2d]/15 border border-[#ff4d2d]/30 grid place-items-center text-[#ff4d2d]"><Sparkles size={13} /></span>
                    <div className="surface !rounded-2xl px-4 py-3 flex gap-1.5">
                      {[0, 1, 2].map((d) => (
                        <span key={d} className="w-1.5 h-1.5 rounded-full bg-[#ff4d2d]" style={{ animation: 'typingDot 1.1s infinite', animationDelay: `${d * 0.15}s` }} />
                      ))}
                    </div>
                  </div>
                </div>
              )}
              <div ref={endRef} />
            </>
          )}
        </div>

        {/* Composer */}
        <div className="p-4 border-t border-[var(--border-default)] bg-[var(--bg-card)]">
          <div className="flex items-center gap-2 p-1.5 pl-4 rounded-2xl bg-[var(--bg-inset)] border border-[var(--border-default)] focus-within:border-[#ff4d2d]/50 focus-within:shadow-[0_0_0_4px_rgba(255,77,45,0.1)] transition-all">
            <input
              type="text"
              className="flex-1 bg-transparent outline-none text-[14px] placeholder:text-[var(--text-muted)] text-[var(--text-primary)]"
              placeholder="Ask about architecture, decisions, or incidents…"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              autoFocus
            />
            <button
              onClick={() => handleSend()}
              disabled={!!pending || !question.trim()}
              className="btn-ripple-primary w-10 h-10 grid place-items-center"
              aria-label="Send"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
