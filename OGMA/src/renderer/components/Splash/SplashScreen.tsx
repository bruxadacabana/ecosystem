import React, { useEffect, useState } from 'react'
import { CosmosLayer } from '../Cosmos/CosmosLayer'
import './SplashScreen.css'

interface Props {
  onDone: () => void
  dark?: boolean
}

export const SplashScreen: React.FC<Props> = ({ onDone, dark = true }) => {
  // Estado para a mensagem cósmica vinda do processo principal
  const [status, setStatus] = useState('Despertando a consciência do sistema...')

  useEffect(() => {
    // ESCUTA O ELECTRON: Aqui recebemos as frases do main.ts
    const removeListener = (window as any).electron.ipcRenderer.on('splash-status', (msg: string) => {
      setStatus(msg)
      
      // Se a mensagem for a de finalização, entramos no app
      if (msg === "A biblioteca universal está atualizada.") {
        setTimeout(onDone, 1500)
      }
    })

    // SEGURANÇA: Se a sincronização falhar, entra no app após 15s
    const timeout = setTimeout(onDone, 15000)

    return () => {
      removeListener()
      clearTimeout(timeout)
    }
  }, [onDone])

  // --- Suas Definições de Cores e Estética ---
  const paperBg = dark ? '#1A1610' : '#F5F0E8'
  const border  = dark ? '#3A3020' : '#C4B9A8'
  const ink     = dark ? '#E8DFC8' : '#2C2416'
  const ink2    = dark ? '#8A7A62' : '#9C8E7A'
  const accent  = dark ? '#D4A820' : '#b8860b'

  return (
    <div className="splash-overlay">
      <div
        className="splash-card"
        style={{ background: paperBg, borderColor: border }}
      >
        {/* Camada Cosmos */}
        <CosmosLayer 
          width={520} 
          height={340} 
          seed="ogma_splash"
          density="high" 
          dark={dark} 
        />

        {/* Linha de margem decorativa */}
        <div className="splash-margin" style={{ background: 'rgba(160,50,30,0.22)' }} />

        {/* Logo Estilizada */}
        <div className="splash-logo" style={{ color: ink }}>
          OGMA
        </div>

        {/* Subtítulo */}
        <div className="splash-sub" style={{ color: ink2 }}>
          GERENCIADOR DE PROJETOS E ESTUDOS
        </div>

        {/* Divisor */}
        <div className="splash-divider" style={{ background: border }} />

        {/* MENSAGEM DINÂMICA: Exibe o status que vem do main.ts */}
        <div className="splash-status" style={{ color: ink, fontWeight: 'bold' }}>
          {status}
        </div>

        {/* Pontos de animação (opcional) */}
        <div className="splash-dots" style={{ color: accent }}>
          · · ·
        </div>

        {/* Versão */}
        <div className="splash-version" style={{ color: ink2 }}>v0.1.0</div>
      </div>
    </div>
  )
}