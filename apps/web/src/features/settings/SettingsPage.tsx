import { Card } from '../../components/ui/Card'
import { Icon, type IconName } from '../../components/ui/Icon'
import { useAppearance } from '../../theme/context'
import { ACCENTS, type AccentName, type ThemeMode } from '../../theme/theme'

const THEME_OPTIONS: { mode: ThemeMode; label: string; hint: string; icon: IconName }[] = [
  { mode: 'light', label: 'Light', hint: 'White and accent', icon: 'sun' },
  { mode: 'dark', label: 'Dark', hint: 'Black and accent', icon: 'moon' },
  { mode: 'system', label: 'System', hint: 'Follow this device', icon: 'monitor' },
]

const ACCENT_NAMES = Object.keys(ACCENTS) as AccentName[]

export function SettingsPage() {
  const { appearance, resolved, update } = useAppearance()

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 px-6 pt-8 pb-12 max-sm:px-4">
      <header className="flex flex-col gap-1">
        <h1 className="m-0 text-[28px] font-semibold tracking-tight">Settings</h1>
        <p className="m-0 text-sm text-muted">Saved on this device. Synced to your account once sign-in arrives.</p>
      </header>

      <Card title="Theme">
        <fieldset className="m-0 grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3 border-none p-0">
          <legend className="sr-only">Theme</legend>
          {THEME_OPTIONS.map((option) => {
            const selected = appearance.mode === option.mode
            return (
              <label
                key={option.mode}
                className={`flex cursor-pointer flex-col gap-3 rounded-xl border-2 p-4 has-focus-visible:outline-2 has-focus-visible:outline-accent ${
                  selected ? 'border-accent bg-accent-soft' : 'border-line hover:border-muted'
                }`}
              >
                <input
                  type="radio"
                  name="theme"
                  value={option.mode}
                  checked={selected}
                  onChange={() => update({ mode: option.mode })}
                  className="sr-only"
                />
                <ThemePreview mode={option.mode} />
                <span className="flex items-center gap-2 text-sm font-semibold">
                  <Icon name={option.icon} size={16} />
                  {option.label}
                </span>
                <span className="text-xs text-muted">{option.hint}</span>
              </label>
            )
          })}
        </fieldset>
        {appearance.mode === 'system' && (
          <p className="m-0 text-xs text-muted">Your device is currently using the {resolved} theme.</p>
        )}
      </Card>

      <Card title="Accent colour">
        <fieldset className="m-0 flex flex-wrap gap-3 border-none p-0">
          <legend className="sr-only">Accent colour</legend>
          {ACCENT_NAMES.map((name) => {
            const selected = appearance.accent === name
            const shade = ACCENTS[name][resolved]
            return (
              <label
                key={name}
                className={`flex min-h-11 cursor-pointer items-center gap-2.5 rounded-full border-2 py-1.5 pr-4 pl-1.5 text-sm font-medium has-focus-visible:outline-2 has-focus-visible:outline-accent ${
                  selected ? 'border-accent' : 'border-line hover:border-muted'
                }`}
              >
                <input
                  type="radio"
                  name="accent"
                  value={name}
                  checked={selected}
                  onChange={() => update({ accent: name })}
                  className="sr-only"
                />
                <span
                  aria-hidden="true"
                  className="flex size-7 items-center justify-center rounded-full"
                  style={{ background: shade.accent, color: shade.onAccent }}
                >
                  {selected && <Icon name="check" size={14} strokeWidth={3} />}
                </span>
                {ACCENTS[name].label}
              </label>
            )
          })}
        </fieldset>
        <div className="flex flex-wrap items-center gap-3 rounded-xl bg-bubble p-4">
          <span className="text-sm text-muted">Preview</span>
          <button
            type="button"
            className="h-10 cursor-pointer rounded-full border-none bg-accent px-4 text-sm font-semibold text-on-accent hover:bg-accent-hover"
          >
            Primary button
          </button>
          <span className="rounded-full bg-accent-soft px-3 py-1 text-xs font-semibold text-accent">Badge</span>
          <span className="text-sm font-medium text-accent underline">Link text</span>
        </div>
      </Card>
    </div>
  )
}

/** A miniature of the app in the given theme. Colours are fixed here on purpose. */
function ThemePreview({ mode }: { mode: ThemeMode }) {
  const light = (
    <div className="flex h-full bg-white">
      <div className="w-1/4 bg-[#f7f8f8]" />
      <div className="flex flex-1 flex-col justify-end gap-1 p-2">
        <div className="h-1.5 w-2/3 self-end rounded-full bg-[#e8ebea]" />
        <div className="h-1.5 w-1/2 rounded-full bg-[#15803d]" />
      </div>
    </div>
  )
  const dark = (
    <div className="flex h-full bg-[#0a0a0a]">
      <div className="w-1/4 bg-black" />
      <div className="flex flex-1 flex-col justify-end gap-1 p-2">
        <div className="h-1.5 w-2/3 self-end rounded-full bg-[#262626]" />
        <div className="h-1.5 w-1/2 rounded-full bg-[#22c55e]" />
      </div>
    </div>
  )
  return (
    <div aria-hidden="true" className="h-16 overflow-hidden rounded-lg border border-line">
      {mode === 'light' && light}
      {mode === 'dark' && dark}
      {mode === 'system' && (
        <div className="grid h-full grid-cols-2">
          {light}
          {dark}
        </div>
      )}
    </div>
  )
}
