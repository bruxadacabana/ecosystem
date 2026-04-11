import React, { useEffect, useRef } from 'react'
import './Modal.css'

interface Props {
  title:        string
  onClose:      () => void
  children:     React.ReactNode
  footer?:      React.ReactNode
  width?:       number
  cosmos?:      boolean
  dark?:        boolean
}

export const Modal: React.FC<Props> = ({
  title, onClose, children, footer, width = 520, cosmos = true, dark = false,
}) => {
  const overlayRef = useRef<HTMLDivElement>(null)

  // Fechar com Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  // Fechar ao clicar no overlay (não no modal)
  const handleOverlayMouseDown = (e: React.MouseEvent) => {
    if (e.target === overlayRef.current) onClose()
  }

  const border = dark ? '#3A3020' : '#C4B9A8'
  const bg     = dark ? '#1A1610' : '#F5F0E8'
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'

  return (
    <div
      ref={overlayRef}
      className="modal-overlay"
      onMouseDown={handleOverlayMouseDown}
    >
      <div
        className="modal paper-fall"
        style={{ width, background: bg, borderColor: border }}
      >
        {/* Cosmos decorativo no canto superior direito */}
        {cosmos && (
          <div className="modal-cosmos" aria-hidden>
            {/* Estrelas simples via CSS */}
            <span className="modal-star s1">✦</span>
            <span className="modal-star s2">✦</span>
            <span className="modal-star s3">✦</span>
          </div>
        )}

        {/* Título */}
        <div className="modal-title" style={{ borderColor: border, color: ink }}>
          {title}
        </div>

        {/* Conteúdo */}
        <div className="modal-body">
          {children}
        </div>

        {/* Rodapé */}
        {footer && (
          <div className="modal-footer" style={{ borderColor: border }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}
