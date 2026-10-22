import { useState, useRef, useEffect } from 'react'
import { MessageSquare, Sparkles, Send, X, Bot, User, ExternalLink, ShieldCheck } from 'lucide-react'

const QUICK_PROMPTS = [
  'Draft bilingual Telugu & English alert',
  'AP Blackspot risk breakdown',
  'Nearest Level-1 trauma centers',
  'Explain active incident protocol',
]

export default function OperatorCopilot({ incident }) {
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: 'Highway Safety Copilot online. I ground responses using Parallel AI web intelligence and Andhra Pradesh road safety protocols. How can I assist with traffic operations?',
      timestamp: Date.now(),
    },
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const chatEndRef = useRef(null)

  useEffect(() => {
    if (isOpen) {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, isOpen])

  const handleSend = async (textToSend) => {
    const query = (textToSend || input).trim()
    if (!query || isLoading) return

    const userMsg = {
      role: 'user',
      text: query,
      timestamp: Date.now(),
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setIsLoading(true)

    try {
      const res = await fetch('/api/copilot/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          incident_id: incident?.id,
        }),
      })

      if (res.ok) {
        const data = await res.json()
        const botMsg = {
          role: 'assistant',
          text: data.reply,
          sources: data.sources || [],
          timestamp: data.timestamp || Date.now(),
        }
        setMessages((prev) => [...prev, botMsg])
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            text: 'Encountered an issue communicating with the intelligence service. Please retry in a moment.',
            timestamp: Date.now(),
          },
        ])
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: 'Unable to reach backend copilot endpoint. Ensure server is active.',
          timestamp: Date.now(),
        },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="copilot-container">
      {/* Floating Trigger Pill */}
      {!isOpen && (
        <button
          type="button"
          className="copilot-toggle-btn"
          onClick={() => setIsOpen(true)}
          title="Open Highway Safety Copilot (On-demand AI)"
        >
          <Sparkles size={15} className="copilot-sparkle" />
          <span>AI Copilot</span>
          <span className="copilot-badge">Parallel</span>
        </button>
      )}

      {/* Floating Chat Drawer */}
      {isOpen && (
        <div className="copilot-drawer">
          <div className="copilot-head">
            <div className="copilot-title">
              <Bot size={17} className="text-emerald" />
              <div>
                <h4>Highway Operations Copilot</h4>
                <span className="copilot-subtitle">Parallel AI Grounded Intelligence</span>
              </div>
            </div>
            <button
              type="button"
              className="copilot-close"
              onClick={() => setIsOpen(false)}
              aria-label="Close Copilot"
            >
              <X size={15} />
            </button>
          </div>

          <div className="copilot-messages">
            {messages.map((m, idx) => (
              <div key={idx} className={`copilot-msg copilot-msg--${m.role}`}>
                <div className="msg-avatar">
                  {m.role === 'assistant' ? <Bot size={13} /> : <User size={13} />}
                </div>
                <div className="msg-bubble">
                  <div className="msg-text" style={{ whiteSpace: 'pre-wrap' }}>{m.text}</div>
                  {m.sources && m.sources.length > 0 && (
                    <div className="msg-sources">
                      <span className="sources-label">Sources:</span>
                      {m.sources.map((s, sIdx) => (
                        <a
                          key={sIdx}
                          href={s.url}
                          target="_blank"
                          rel="noreferrer"
                          className="source-link"
                          title={s.snippet || s.title}
                        >
                          <ExternalLink size={10} />
                          {s.title.slice(0, 32)}...
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="copilot-msg copilot-msg--assistant">
                <div className="msg-avatar"><Bot size={13} /></div>
                <div className="msg-bubble copilot-typing">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Quick Prompts */}
          <div className="copilot-prompts">
            {QUICK_PROMPTS.map((prompt, pIdx) => (
              <button
                key={pIdx}
                type="button"
                className="prompt-chip"
                onClick={() => handleSend(prompt)}
                disabled={isLoading}
              >
                {prompt}
              </button>
            ))}
          </div>

          {/* Input Bar */}
          <form
            className="copilot-input-form"
            onSubmit={(e) => {
              e.preventDefault()
              handleSend()
            }}
          >
            <input
              type="text"
              className="copilot-input"
              placeholder="Ask copilot or draft advisory..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={isLoading}
            />
            <button
              type="submit"
              className="copilot-send-btn"
              disabled={!input.trim() || isLoading}
              aria-label="Send query"
            >
              <Send size={13} />
            </button>
          </form>
        </div>
      )}
    </div>
  )
}
