export default function Placeholder({ title, phase }) {
  return (
    <div>
      <h1 className="mb-3 text-xl font-semibold">{title}</h1>
      <p className="ph">Belum dibangun. Dikerjakan di {phase}.</p>
    </div>
  )
}
