import React, { useState } from 'react';
import {
  MessageSquare,
  Send,
  Sparkles,
  Link2,
  AlertTriangle,
  FileText,
  HelpCircle,
  X,
} from 'lucide-react';
import type { AskBrainResponse } from '../api';

interface AskBrainDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onAsk: (question: string) => Promise<AskBrainResponse>;
  onSelectNodeId?: (nodeId: string) => void;
}

export const AskBrainDrawer: React.FC<AskBrainDrawerProps> = ({
  isOpen,
  onClose,
  onAsk,
  onSelectNodeId,
}) => {
  const [question, setQuestion] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [history, setHistory] = useState<AskBrainResponse[]>([]);

  if (!isOpen) return null;

  const handleSend = async (qToSend?: string) => {
    const q = qToSend || question;
    if (!q.trim() || isLoading) return;

    setIsLoading(true);
    try {
      const resp = await onAsk(q);
      setHistory((prev) => [resp, ...prev]);
      setQuestion('');
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const sampleQuestions = [
    'Who owns the payment service and who actually knows it?',
    'Why did we choose gRPC for checkout communication?',
    'What breaks if currency service goes down?',
    'Which docs describing checkout might be out of date?',
  ];

  return (
    <div className="ask-drawer-backdrop" onClick={onClose}>
      <div className="ask-drawer glass-panel" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <div className="drawer-title-group">
            <MessageSquare size={16} className="text-cyan" />
            <h3>Ask Company Brain (Track 3)</h3>
          </div>
          <button className="close-btn" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        {/* Question Input */}
        <div className="drawer-input-row">
          <input
            type="text"
            className="drawer-input"
            placeholder="Ask anything about architecture, decisions, or incidents..."
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          />
          <button
            className="drawer-send-btn"
            onClick={() => handleSend()}
            disabled={isLoading || !question.trim()}
          >
            <Send size={15} />
          </button>
        </div>

        {/* Sample chips */}
        <div className="sample-chips">
          {sampleQuestions.map((sq, i) => (
            <button
              key={i}
              className="sample-chip"
              onClick={() => handleSend(sq)}
              disabled={isLoading}
            >
              {sq}
            </button>
          ))}
        </div>

        {/* Conversation Responses */}
        <div className="drawer-scroll-body">
          {history.length === 0 ? (
            <div className="empty-drawer">
              <Sparkles size={24} className="text-muted" />
              <p>Natural-language Q&amp;A answered directly from graph facts with verifiable citations.</p>
            </div>
          ) : (
            history.map((item, idx) => (
              <div key={idx} className="qa-card">
                <div className="qa-question">
                  <span className="q-label">Q:</span>
                  <strong>{item.question}</strong>
                </div>

                <div className="qa-answer">
                  <p>{item.answer}</p>
                </div>

                {/* Sources & Citations */}
                {item.sources && item.sources.length > 0 && (
                  <div className="qa-citations">
                    <span className="cite-title"><Link2 size={12} /> Graph Citations:</span>
                    <div className="cite-chips">
                      {item.sources.map((src, sIdx) => (
                        <div
                          key={sIdx}
                          className={`cite-chip ${src.stale ? 'stale' : ''} ${src.superseded ? 'superseded' : ''}`}
                          onClick={() => onSelectNodeId?.(src.id)}
                          title="Click to locate node on graph canvas"
                        >
                          <span className="cite-id">{src.id}</span>
                          {src.stale && <span className="stale-badge">STALE</span>}
                          {src.superseded && <span className="superseded-badge">SUPERSEDED</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
