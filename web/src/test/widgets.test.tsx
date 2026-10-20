import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CompareColumn, Widget } from '@/contracts/types'
import { fixtures } from '@/dev/fixtures'
import i18n from '@/i18n'
import { ApiError } from '@/lib/api'
import { WidgetEnvContext, type WidgetEnv } from '@/widgets/env'
import type { Emit } from '@/widgets/types'
import { WidgetView } from '@/widgets/WidgetView'
import { rendererFor, widgetRenderers } from '@/widgets/registry'
import { ALL_WIDGET_TYPES } from '@/widgets/types'
import widgetSchema from '@/contracts/widget.schema.json?raw'
import geo from '@/dev/planning_areas.sample.geojson?raw'

const fx = (name: string): Widget => {
  const f = fixtures.find((x) => x.name === name)
  if (!f) throw new Error(`no fixture ${name}`)
  return structuredClone(f.widget)
}

function setup(widget: Widget, opts: { readOnly?: boolean; disabled?: boolean; env?: Partial<WidgetEnv> } = {}) {
  const emit = vi.fn<Emit>()
  const env: WidgetEnv = {
    resolveUrl: (u) => u,
    previewSetaside: vi.fn(),
    previewCompare: vi.fn(),
    upload: vi.fn(async () => ({ doc_id: 'doc_new' })),
    openTab: vi.fn(),
    ...opts.env,
  }
  const ui = (w: Widget): ReactElement => (
    <WidgetEnvContext.Provider value={env}>
      <WidgetView name={w.payload.type!} widget={w} complete emit={emit} readOnly={opts.readOnly} disabled={opts.disabled} />
    </WidgetEnvContext.Provider>
  )
  const utils = render(ui(widget))
  return { emit, env, ...utils, user: userEvent.setup() }
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      String(url).includes('planning_areas') ? new Response(geo, { status: 200 }) : new Response('{}', { status: 404 }),
    ),
  )
})
afterEach(() => vi.unstubAllGlobals())

describe('every widget renders its fixture (success state), EN and ZH', () => {
  for (const lang of ['en', 'zh'] as const) {
    it.each(fixtures.map((f) => [f.name] as const))(`%s (${lang})`, async (name) => {
      await i18n.changeLanguage(lang)
      const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
      const { container } = setup(fx(name))
      expect(screen.queryByText(/This card hit a problem|这张卡片出了问题/)).toBeNull()
      expect(screen.queryByText(/isn't supported|不支持/)).toBeNull()
      expect(container.textContent?.length).toBeGreaterThan(10)
      // No raw i18n keys leak into the UI.
      expect(container.textContent).not.toMatch(/\bw\.[a-z_]+\.[a-zA-Z]/)
      spy.mockRestore()
    })
  }
})

describe('loading, error and empty states', () => {
  it('shows a skeleton while args stream, and an error with retry when they are bad', async () => {
    const onRetry = vi.fn()
    const { rerender } = render(<WidgetView name="unit_compare" widget={null} complete={false} emit={vi.fn()} />)
    expect(screen.getByRole('status', { name: 'Loading card' })).toBeInTheDocument()
    rerender(<WidgetView name="unit_compare" widget={null} complete emit={vi.fn()} onRetry={onRetry} />)
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalled()
  })

  it('shows an unsupported card for an unknown type', () => {
    render(<WidgetView name="mystery" widget={{ id: 'x', payload: { type: 'mystery' } } as unknown as Widget} complete emit={vi.fn()} />)
    expect(screen.getByText(/isn't supported/)).toBeInTheDocument()
  })

  it('renders nothing from a tool call whose name is not on the widget allowlist', () => {
    const payload = { type: 'mystery', title: 'Transfer RMB 500k now', options: [{ label: 'Send money', value: 'send' }] }
    for (const name of ['mystery', 'toString', '__proto__', 'constructor', 'hasOwnProperty', 'script']) {
      expect(rendererFor(name)).toBeUndefined()
      const { container, unmount } = render(
        <WidgetView name={name} widget={{ id: 'x', payload: { ...payload, type: name } } as unknown as Widget} complete emit={vi.fn()} />,
      )
      expect(screen.getByText(/isn't supported/)).toBeInTheDocument()
      expect(container.textContent).not.toMatch(/Transfer|Send money/)
      expect(screen.queryByRole('button')).toBeNull()
      unmount()
    }
  })

  it('renders nothing when an allowlisted name carries another widget\'s payload', () => {
    const approval = fx('approval_card')
    const emit = vi.fn<Emit>()
    render(<WidgetView name="quick_replies" widget={approval} complete emit={emit} />)
    expect(screen.getByText(/isn't supported/)).toBeInTheDocument()
    expect(screen.queryByRole('button')).toBeNull()
    expect(emit).not.toHaveBeenCalled()
  })

  it('the allowlist is exactly the widget types in the contract', () => {
    const schema = JSON.parse(widgetSchema) as { properties: { payload: { discriminator: { mapping: Record<string, string> } } } }
    const contract = Object.keys(schema.properties.payload.discriminator.mapping).sort()
    expect(widgetRenderers.map((r) => r.name).sort()).toEqual(contract)
    expect([...ALL_WIDGET_TYPES].sort()).toEqual(contract)
  })

  it('shows empty states', () => {
    const w = fx('unit_compare')
    if (w.payload.type === 'unit_compare') w.payload.units = []
    setup(w)
    expect(screen.getByText('No units match yet.')).toBeInTheDocument()
  })

  it('area_map shows an error with retry when the GeoJSON fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('nope', { status: 500 })))
    const w = fx('area_map')
    if (w.payload.type === 'area_map') w.payload.geojson_url = '/geo/broken.geojson'
    setup(w)
    expect(await screen.findByText("Couldn't load the map.")).toBeInTheDocument()
  })
})

describe('widget events', () => {
  it('quick_replies: default first, tap sends reply', async () => {
    const { emit, user } = setup(fx('quick_replies'))
    const buttons = screen.getAllByRole('button')
    expect(buttons[0]).toHaveTextContent('Near my kind of customer')
    await user.click(screen.getByRole('button', { name: /Low rent/ }))
    expect(emit).toHaveBeenCalledWith('reply', { value: 'low_rent', data: { slot: 'priority' }, label: 'Low rent' })
    expect(screen.getByRole('button', { name: /Foot traffic/ })).toBeDisabled()
  })

  it('profile_card: edit a field (validated) then confirm', async () => {
    const { emit, user } = setup(fx('profile_card'))
    await user.click(screen.getByRole('button', { name: 'Edit Monthly operating profit' }))
    const input = screen.getByLabelText('Monthly operating profit')
    await user.type(input, 'abc')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Enter an amount')
    await user.clear(input)
    await user.type(input, '450000')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(emit).toHaveBeenCalledWith('edit', { value: '450000', data: { field: 'profit', value: '450000' }, label: 'Monthly operating profit: RMB 450000' }),
    )
    await user.click(screen.getByRole('button', { name: "That's right" }))
    expect(emit).toHaveBeenLastCalledWith('confirm', { label: "That's right" })
  })

  it('consent_card: agree', async () => {
    const { emit, user } = setup(fx('consent_card'))
    await user.click(screen.getByRole('button', { name: 'Agree' }))
    expect(emit).toHaveBeenCalledWith('consent', { value: true, data: { granted: true }, label: 'Agree' })
  })

  it('area_map: picking a top area sends select_area', async () => {
    const { emit, user } = setup(fx('area_map'))
    await user.click(screen.getByRole('button', { name: 'See Jurong East' }))
    expect(emit).toHaveBeenCalledWith('select_area', { value: 'JURONG EAST', data: { id: 'JURONG EAST' }, label: 'Jurong East' })
  })

  it('area_map: keyboard users can pick any area from the list', async () => {
    const { emit, user } = setup(fx('area_map'))
    await user.selectOptions(screen.getByLabelText('Or pick another area'), 'WOODLANDS')
    expect(emit).toHaveBeenCalledWith('select_area', expect.objectContaining({ value: 'WOODLANDS' }))
  })

  it('area_card: shortlist and back', async () => {
    const { emit, user } = setup(fx('area_card'))
    await user.click(screen.getByRole('button', { name: 'Shortlist this area' }))
    expect(emit).toHaveBeenCalledWith('shortlist', expect.objectContaining({ value: 'TAMPINES', data: { id: 'TAMPINES' } }))
  })

  it('unit_compare: pick a unit', async () => {
    const { emit, user } = setup(fx('unit_compare'))
    await user.click(screen.getAllByRole('button', { name: 'Cost this unit' })[1]!)
    expect(emit).toHaveBeenCalledWith('select_unit', { value: 'u2', data: { id: 'u2' }, label: 'Century Square #B1-08' })
  })

  it('cost_breakdown: edit a line and confirm; read_only variant has no actions', async () => {
    const { emit, user } = setup(fx('cost_breakdown'))
    await user.click(screen.getByRole('button', { name: /Fit-out and equipment/ }))
    await user.click(screen.getByRole('button', { name: 'Edit Equipment and POS' }))
    await user.type(screen.getByLabelText('New amount for Equipment and POS'), '61,500')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(emit).toHaveBeenCalledWith('edit_line', {
        value: '61500',
        data: { id: 'equipment', value: '61500', currency: 'SGD' },
        label: 'Equipment and POS: S$61500',
      }),
    )
    await user.click(screen.getByRole('button', { name: 'Use this cost' }))
    expect(emit).toHaveBeenLastCalledWith('confirm', { label: 'Use this cost' })
  })

  it('cost_breakdown read_only: no edit or confirm', () => {
    setup(fx('cost_breakdown.read_only'))
    expect(screen.queryByRole('button', { name: 'Use this cost' })).toBeNull()
    expect(screen.queryByRole('button', { name: /^Edit / })).toBeNull()
  })

  it('cost_breakdown: "Where\'s this from?" shows the source and taint note', async () => {
    const { user } = setup(fx('cost_breakdown'))
    await user.click(screen.getByRole('button', { name: /S\$390,550\. Where is this from/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Calculated by Waypoint')).toBeInTheDocument()
    expect(within(dialog).getByText('estimate_costs')).toBeInTheDocument()
  })

  it('upload_prompt: uploads then sends the doc id', async () => {
    const { emit, env } = setup(fx('upload_prompt'))
    const file = new File(['x'], 'quote.jpg', { type: 'image/jpeg' })
    const camera = document.querySelector('input[capture="environment"]') as HTMLInputElement
    expect(camera).toHaveAttribute('accept', 'image/*')
    fireEvent.change(camera, { target: { files: [file] } })
    await waitFor(() => expect(emit).toHaveBeenCalledWith('upload', { value: 'doc_new', data: { doc_id: 'doc_new', filename: 'quote.jpg' }, label: 'Uploaded quote.jpg' }))
    expect(env.upload).toHaveBeenCalledWith(file)
  })

  it.each([
    [413, /over 10 MB/],
    [429, /a lot of uploads in a short time/],
  ])('upload_prompt: a %i from the server shows a plain message', async (status, text) => {
    const upload = vi.fn(async () => {
      throw new ApiError(status, 'detail')
    })
    setup(fx('upload_prompt'), { env: { upload } })
    const camera = document.querySelector('input[capture="environment"]') as HTMLInputElement
    fireEvent.change(camera, { target: { files: [new File(['x'], 'quote.jpg', { type: 'image/jpeg' })] } })
    expect(await screen.findByText(text)).toBeInTheDocument()
  })

  it('upload_prompt (demo): the sample quote photo goes through the normal upload path', async () => {
    const sample = new File(['png'], 'sample-quote.png', { type: 'image/png' })
    const { emit, env, user } = setup(fx('upload_prompt'), { env: { sampleQuote: vi.fn(async () => sample) } })
    await user.click(screen.getByRole('button', { name: 'Use the sample quote photo' }))
    await waitFor(() => expect(env.upload).toHaveBeenCalledWith(sample))
    expect(emit).toHaveBeenCalledWith('upload', { value: 'doc_new', data: { doc_id: 'doc_new', filename: 'sample-quote.png' }, label: 'Uploaded sample-quote.png' })
  })

  it('upload_prompt: no sample button outside demo mode', () => {
    setup(fx('upload_prompt'))
    expect(screen.queryByRole('button', { name: 'Use the sample quote photo' })).toBeNull()
  })

  it('upload_prompt extracted: accept and reject lines; untrusted figures say so', async () => {
    const { emit, user } = setup(fx('upload_prompt.extracted'))
    await user.click(screen.getByRole('button', { name: 'Accept Flooring and ceiling' }))
    expect(emit).toHaveBeenCalledWith('accept_line', { value: 'l2', data: { id: 'l2' }, label: 'Accept Flooring and ceiling' })
    await user.click(screen.getByRole('button', { name: 'Reject Signage' }))
    expect(emit).toHaveBeenCalledWith('reject_line', { value: 'l3', data: { id: 'l3' }, label: 'Reject Signage' })
    await user.click(screen.getByRole('button', { name: /S\$42,000\. Where is this from/ }))
    expect(await screen.findByText(/isn't used until you accept it/)).toBeInTheDocument()
  })

  it('upload_prompt extracted: "Accept all lines" accepts the pending lines and leaves "please check" ones to confirm', async () => {
    const { emit, user } = setup(fx('upload_prompt.extracted'))
    expect(screen.getByText('1 line is marked "Please check": accept or reject it on its own.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Accept all lines' }))
    expect(emit).toHaveBeenCalledWith('accept_all', { value: 'doc_q1', data: { doc_id: 'doc_q1' }, label: 'Accept all lines (1)' })
    expect(screen.queryByRole('button', { name: 'Accept all lines' })).toBeNull()
    expect(screen.getAllByText('Accepted')).toHaveLength(2)
    // the low-confidence line still has its own buttons
    await user.click(screen.getByRole('button', { name: 'Accept Signage' }))
    expect(emit).toHaveBeenCalledWith('accept_line', { value: 'l3', data: { id: 'l3' }, label: 'Accept Signage' })
    expect(screen.queryByText(/marked "Please check"/)).toBeNull()
  })

  it('upload_prompt extracted: a part line says the estimate stays; the owner can say the quote covers all of it', async () => {
    const { emit, user } = setup(fx('upload_prompt.extracted'))
    expect(screen.getAllByText('Part of: Fit-out (the estimate stays)')).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Only part' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByRole('button', { name: 'All of it' }))
    expect(emit).toHaveBeenCalledWith('set_coverage', {
      value: 'fitout',
      data: { doc_id: 'doc_q1', key: 'fitout', whole: true },
      label: 'This quote covers all of Fit-out',
    })
    expect(screen.getByRole('button', { name: 'All of it' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getAllByText('Replaces: Fit-out')).toHaveLength(2)
  })

  it('upload_prompt extracted: an unmatched line is left for the owner to assign', async () => {
    const { emit, user } = setup(fx('upload_prompt.extracted'))
    const selects = screen.getAllByLabelText('Which cost is this?')
    expect(selects).toHaveLength(2)
    await user.selectOptions(selects[0]!, 'equipment_pos')
    expect(emit).toHaveBeenCalledWith('assign_line', { value: 'l3', data: { id: 'l3', key: 'equipment_pos' }, label: 'Signage is for Equipment and POS' })
  })

  it('upload_prompt extracted (read-only): unmatched lines say so, no controls', () => {
    setup(fx('upload_prompt.extracted'), { readOnly: true })
    expect(screen.queryByLabelText('Which cost is this?')).toBeNull()
    expect(screen.getAllByText('Not matched to a cost')).toHaveLength(2)
    expect(screen.queryByRole('button', { name: 'All of it' })).toBeNull()
  })

  it('cost_breakdown: quote checks show on the line', async () => {
    const { user } = setup(fx('cost_breakdown'))
    for (const b of screen.getAllByRole('button')) if (b.getAttribute('aria-expanded') === 'false') await user.click(b)
    expect(screen.getByText('Quote below estimate')).toBeInTheDocument()
    expect(screen.getByText('Part quoted')).toBeInTheDocument()
  })

  it('unit_compare: break-even is compared with the best and the average shop', () => {
    setup(fx('unit_compare'))
    expect(screen.getAllByText('Your best shop:').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Your average shop:').length).toBe(screen.getAllByText('Your best shop:').length)
  })

  it('missing_items: mark included and add a value', async () => {
    const { emit, user } = setup(fx('missing_items'))
    await user.click(screen.getAllByRole('button', { name: "It's included" })[0]!)
    expect(emit).toHaveBeenCalledWith('mark_included', { value: 'demolition', data: { id: 'demolition' }, label: 'Demolition is included' })
    await user.click(screen.getByRole('button', { name: 'Add a cost' }))
    await user.type(screen.getByLabelText('Amount for Electrical upgrade'), '4000')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(emit).toHaveBeenLastCalledWith('edit_line', expect.objectContaining({ value: '4000', data: { id: 'electrical', value: '4000', currency: 'SGD' } })))
  })

  it('funding_options: toggle an option', async () => {
    const { emit, user } = setup(fx('funding_options'))
    await user.click(screen.getByRole('switch', { name: 'Your own savings, as capital' }))
    expect(emit).toHaveBeenCalledWith('toggle_option', { value: true, data: { id: 'savings', on: true }, label: 'Include Your own savings, as capital' })
  })

  it('funding_options: WeBank cards are read-only, dated, and carry the R2 pause', () => {
    setup(fx('funding_options'))
    const banks = screen.getByRole('region', { name: 'What WeBank says yes to, at home' })
    expect(within(banks).queryAllByRole('switch')).toHaveLength(0)
    expect(within(banks).getAllByText('Not in the Singapore plan')).toHaveLength(2)
    expect(within(banks).getByText('RMB 150k')).toBeInTheDocument()
    expect(within(banks).getByText(/your Singapore set-aside and transfers pause/)).toBeInTheDocument()
    expect(within(banks).getAllByText(/As of 2026-10-20/).length).toBe(2)
    expect(within(banks).getByText('Your ODI bank')).toBeInTheDocument()
    expect(within(banks).getByRole('link', { name: 'WeBank 微业贷 product page' })).toHaveAttribute('href', expect.stringContaining('webank.com'))
  })

  it('funding_options: the after-opening view is read-only and never in the plan', () => {
    setup(fx('funding_options'))
    const later = screen.getByRole('region', { name: 'After opening' })
    expect(within(later).queryAllByRole('switch')).toHaveLength(0)
    expect(within(later).getByText(/no trading-history test/)).toBeInTheDocument()
    expect(within(later).getByRole('link', { name: /EFS SME Working Capital Loan/ })).toHaveAttribute('href', expect.stringContaining('enterprisesg.gov.sg'))
  })

  it('funding_options: ranked routes carry words, never a score, and why; routes not open yet have no switch', () => {
    setup(fx('funding_options'))
    expect(screen.getByText(/In order for you: cheapest first/)).toBeInTheDocument()
    const plan = screen.getAllByRole('switch').map((s) => s.closest('li')!)
    expect(plan[0]).toHaveTextContent('Spare cash (home company)') // the ranked order the payload carries
    const top = plan[0]
    for (const w of ['Costs nothing', 'Fastest', 'Keeps full ownership']) expect(within(top).getByText(w)).toBeInTheDocument()
    expect(within(top).getByText('Raises floor risk')).toBeInTheDocument()
    const why = within(top).getByRole('region', { name: 'Why it’s here in the order' })
    expect(within(why).getByText('Change in floor risk')).toBeInTheDocument()
    expect(within(why).getByText('3.3%')).toBeInTheDocument()
    expect(screen.queryByText(/score/i)).toBeNull()
    const notYet = screen.getByRole('region', { name: 'Not open to you yet' })
    expect(within(notYet).getByText('Local partner equity')).toBeInTheDocument()
    expect(within(notYet).getByText(/Only if you would consider a local partner/)).toBeInTheDocument()
    expect(within(notYet).queryAllByRole('switch')).toHaveLength(0)
    expect(screen.queryByRole('switch', { name: 'Local partner equity' })).toBeNull()
  })

  it('goal_summary: figure labels follow the UI language', async () => {
    await i18n.changeLanguage('zh')
    setup(fx('goal_summary'))
    for (const label of ['预计开业', '情况不理想时开业', '每月储蓄', '跌破安全线的风险']) expect(screen.getByText(label)).toBeInTheDocument()
    expect(screen.queryByText('Likely opening')).toBeNull()
  })

  it('funding_options: optional routes are compact rows with a details disclosure', async () => {
    const { user } = setup(fx('funding_options'))
    expect(screen.getByText('Only cash above your safety floor and payroll buffer')).toBeInTheDocument()
    expect(screen.queryByText('Never borrowed money')).toBeNull()
    const more = screen.getByRole('button', { name: 'Details for Your own savings, as capital' })
    expect(more).toHaveAttribute('aria-expanded', 'false')
    await user.click(more)
    expect(more).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Never borrowed money')).toBeInTheDocument()
  })

  it('closed_options: collapsed, expands to rules', async () => {
    const user = userEvent.setup()
    setup(fx('closed_options'))
    expect(screen.queryByText('Rule R1')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Why not my WeBank loan?' }))
    expect(screen.getByText('Rule R1')).toBeInTheDocument()
  })

  it('setaside_slider: keyboard preview fetches, the wall blocks, release commits', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const base = fx('setaside_slider')
    const preview = vi.fn(async (_u: string, share: number) => ({
      chart: (base.payload as { chart: never }).chart,
      figures: {},
      display: { f_open: `preview ${share}` },
    }))
    const { emit } = setup(base, { env: { previewSetaside: preview } })
    const slider = screen.getByRole('slider', { name: 'Share of monthly profit to set aside' })
    expect(slider).toHaveAttribute('aria-valuenow', '0.4')
    act(() => slider.focus())
    fireEvent.keyDown(slider, { key: 'ArrowRight' })
    expect(slider).toHaveAttribute('aria-valuenow', '0.45')
    await act(async () => vi.advanceTimersByTime(150))
    expect(preview).toHaveBeenCalledWith('/api/preview/setaside', 0.45, expect.any(AbortSignal))
    expect(await screen.findByText('preview 0.45')).toBeInTheDocument()
    // Past the wall (0.55) the value stays at the wall.
    fireEvent.keyDown(slider, { key: 'End' })
    expect(slider).toHaveAttribute('aria-valuenow', '0.55')
    await act(async () => vi.advanceTimersByTime(800))
    vi.useRealTimers()
    // Keyboard commits are debounced, so one commit for the final value.
    expect(emit).toHaveBeenCalledTimes(1)
    expect(emit).toHaveBeenCalledWith('slider_commit', { value: 0.55, data: { share: 0.55 }, label: 'Set aside 55%' })
    expect(screen.getByText(/higher shares are locked/)).toBeInTheDocument()
  })

  it('milestone_timeline: open a milestone', async () => {
    const { emit, user } = setup(fx('milestone_timeline'))
    await user.click(screen.getByRole('button', { name: 'Open Bank ODI registration' }))
    expect(emit).toHaveBeenCalledWith('open_milestone', { value: 'm3', data: { id: 'm3' }, label: 'Bank ODI registration' })
  })

  it('milestone_timeline (goal): done steps are ticked; only a step code allows can be marked done', async () => {
    const { emit, user } = setup(fx('milestone_timeline.goal'))
    expect(screen.getByText(/^Done on /)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mark Lender consent (WeBank) as done' })).toBeNull()
    expect(screen.queryByRole('button', { name: /Mark Bank ODI registration/ })).toBeNull()
    await user.click(screen.getByRole('button', { name: /^Mark ODI filing .* as done$/ }))
    expect(emit).toHaveBeenCalledWith('mark_milestone_done', expect.objectContaining({ value: 'odi_filing' }))
  })

  it('milestone_timeline (goal, Goal tab): read-only, no mark-done button', () => {
    setup(fx('milestone_timeline.goal'), { readOnly: true })
    expect(screen.queryByRole('button', { name: /as done$/ })).toBeNull()
  })

  it('draft_card: copy puts the letter, its facts and "you send it" on the clipboard; download saves a text file', async () => {
    const w = fx('draft_card')
    const { user } = setup(w)
    const writeText = vi.fn(async () => {})
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    await user.click(screen.getByRole('button', { name: /^Copy / }))
    expect(writeText).toHaveBeenCalledTimes(1)
    const text = String((writeText.mock.calls[0] as unknown[])[0])
    expect(text).toContain(w.payload.type === 'draft_card' ? w.payload.subject : '')
    expect(text).toContain(w.display!['draft.invest_total']!)
    expect(text).toContain('You send this yourself. Waypoint never sends it.')
    expect(screen.getByRole('button', { name: /^Copy / })).toHaveTextContent('Copied')
    const createObjectURL = vi.fn(() => 'blob:x')
    const revokeObjectURL = vi.fn()
    Object.assign(URL, { createObjectURL, revokeObjectURL })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    await user.click(screen.getByRole('button', { name: /^Download / }))
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(click).toHaveBeenCalledTimes(1)
    click.mockRestore()
  })

  it('draft_card: a failed copy says so and points to Download', async () => {
    const { user } = setup(fx('draft_card.checklist'))
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: vi.fn(async () => { throw new Error('denied') }) }, configurable: true })
    await user.click(screen.getByRole('button', { name: /^Copy / }))
    expect(screen.getByRole('alert')).toHaveTextContent("Couldn't copy")
  })

  it('draft_card: a letter whose text could not be written still shows its facts', () => {
    const w = fx('draft_card')
    if (w.payload.type === 'draft_card') w.payload.body = ''
    setup(w)
    expect(screen.getByText(/letter text isn't written yet/)).toBeInTheDocument()
    expect(screen.getByText('Planned investment (likely)')).toBeInTheDocument()
  })

  it('goal_summary: no button of its own (the approval card is the one confirmation)', () => {
    setup(fx('goal_summary'))
    expect(screen.queryByRole('button', { name: 'Looks right' })).toBeNull()
  })

  it('approval_card: approve sends the nonce and card hash', async () => {
    const { emit, user } = setup(fx('approval_card'))
    await user.click(screen.getByRole('button', { name: 'Approve' }))
    expect(emit).toHaveBeenCalledWith('approve', {
      value: 'n_7f3a',
      data: { action: 'create_goal', card_hash: 'sha256:4b1e…', nonce: 'n_7f3a' },
      label: 'Approve: Start my goal',
    })
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  })

  it('approval_card refused: shows the refusal, no buttons', () => {
    setup(fx('approval_card.refused'))
    expect(screen.getByText("Couldn't go ahead")).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
  })

  it('status_card: opens the Goal tab (no event)', async () => {
    const { emit, env, user } = setup(fx('status_card'))
    await user.click(screen.getByRole('button', { name: 'Open the Goal tab' }))
    expect(env.openTab).toHaveBeenCalledWith('goal')
    expect(emit).not.toHaveBeenCalled()
  })

  it('alert_card: a resolved alert offers no fix', () => {
    const w = fx('alert_card')
    setup({ ...w, payload: { ...w.payload, resolved: true } } as typeof w)
    expect(screen.queryByRole('button', { name: 'See fixes' })).toBeNull()
  })

  it('alert_card: see fixes', async () => {
    const { emit, user } = setup(fx('alert_card'))
    await user.click(screen.getByRole('button', { name: 'See fixes' }))
    expect(emit).toHaveBeenCalledWith('see_repairs', { value: 'a_12', data: { id: 'a_12' }, label: 'See fixes' })
  })

  it('repair_options: pick a fix', async () => {
    const { emit, user } = setup(fx('repair_options'))
    await user.click(screen.getAllByRole('button', { name: 'Choose this fix' })[1]!)
    expect(emit).toHaveBeenCalledWith('select_repair', { value: 'r2', data: { id: 'r2', alert_id: 'a_12' }, label: 'Add RMB 0.2m of your own savings' })
  })

  it('rule_card: pick a lawful option', async () => {
    const { emit, user } = setup(fx('rule_card'))
    await user.click(screen.getByRole('button', { name: /Set aside 5% more/ }))
    expect(emit).toHaveBeenCalledWith('select_option', { value: 'raise_share', data: { id: 'raise_share', rule_id: 'R1' }, label: 'Set aside 5% more' })
  })

  it('rule_card: labels a law and a design rule differently', () => {
    const law = setup(fx('rule_card'))
    expect(screen.getByText('Law')).toHaveAttribute('data-kind', 'law')
    law.unmount()
    const w = fx('rule_card')
    if (w.payload.type !== 'rule_card') throw new Error('fixture')
    w.payload.source = { ...w.payload.source, kind: 'design' }
    setup(w)
    expect(screen.getByText('Design rule')).toHaveAttribute('data-kind', 'design')
    expect(screen.queryByText('Law')).toBeNull()
  })

  it('topic_card: tell me more expands without an event', async () => {
    const { emit, user } = setup(fx('topic_card'))
    await user.click(screen.getByRole('button', { name: /Tell me more/ }))
    expect(screen.getByText(/nominee director/)).toBeInTheDocument()
    expect(emit).not.toHaveBeenCalled()
  })

  it('confirm_card: confirm or go back', async () => {
    const { emit, user } = setup(fx('confirm_card'))
    await user.click(screen.getByRole('button', { name: 'Yes, cost it' }))
    expect(emit).toHaveBeenCalledWith('confirm', { value: 'site', data: { step: 'site' }, label: 'Yes, cost it' })
  })

  it('checkin_form: validates, then sends both amounts', async () => {
    const { emit, user } = setup(fx('checkin_form'))
    await user.click(screen.getByRole('button', { name: 'Send' }))
    expect((await screen.findAllByRole('alert')).length).toBe(2)
    await user.type(screen.getByLabelText('Operating profit'), '-20000')
    await user.type(screen.getByLabelText('Amount set aside'), '150000')
    await user.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() =>
      expect(emit).toHaveBeenCalledWith('checkin', {
        value: { profit_cny: '-20000', set_aside_cny: '150000' },
        data: { goal_id: 'g_1', profit_cny: '-20000', set_aside_cny: '150000' },
        label: 'Check-in for September 2026',
      }),
    )
  })

  it('checkin_form from an email link: sends the email period with the amounts', async () => {
    const w = fx('checkin_form')
    w.payload = { ...w.payload, period: 'w4' } as typeof w.payload
    const { emit, user } = setup(w)
    await user.type(screen.getByLabelText('Operating profit'), '90000')
    await user.type(screen.getByLabelText('Amount set aside'), '10000')
    await user.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() =>
      expect(emit).toHaveBeenCalledWith('checkin', expect.objectContaining({ data: { goal_id: 'g_1', profit_cny: '90000', set_aside_cny: '10000', period: 'w4' } })),
    )
  })

  it('plan_vs_actual: toggles series', async () => {
    const user = userEvent.setup()
    setup(fx('plan_vs_actual'))
    expect(screen.getByRole('img', { name: /savings planned/ })).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Profit' }))
    expect(screen.getByRole('img', { name: /profit planned/ })).toBeInTheDocument()
  })

  it('plan_summary: "Change in chat" opens the chat and sends reopen_step, even read-only', async () => {
    const { emit, env, user } = setup(fx('plan_summary.cost'), { readOnly: true })
    await user.click(screen.getByRole('button', { name: 'Change in chat' }))
    expect(env.openTab).toHaveBeenCalledWith('chat')
    expect(emit).toHaveBeenCalledWith('reopen_step', { value: 'cost', data: { step: 'cost' }, label: 'Change my cost' })
  })

  it('disabled widgets do not emit', async () => {
    const { emit, user } = setup(fx('quick_replies'), { disabled: true })
    await user.click(screen.getByRole('button', { name: /Low rent/ }))
    expect(emit).not.toHaveBeenCalled()
  })
})


describe('funding_compare', () => {
  const head = (column: string) => document.querySelector(`th[data-column="${column}"]`) as HTMLElement
  const row = (name: string) => document.querySelector(`tr[data-row="${name}"]`) as HTMLElement

  it('shows each column as code-computed figures, the slider share, and the floor risk with its upper bound', async () => {
    await i18n.changeLanguage('en')
    setup(fx('funding_compare'))
    expect(screen.getByRole('group', { name: 'Compare funding plans' })).toBeInTheDocument()
    expect(screen.getByText('40%')).toBeInTheDocument()
    const opening = row('open_likely')
    expect(within(opening).getByText('month 18.5 (May 2028)')).toBeInTheDocument()
    expect(within(opening).getByText('month 16.5 (Mar 2028)')).toBeInTheDocument()
    const risk = row('floor_risk')
    expect(within(risk).getByText('2.8%')).toBeInTheDocument()
    expect(within(risk).getAllByText('at most').length).toBe(2)
    expect(screen.getByLabelText('Extra savings for Set-aside + your savings, in RMB')).toHaveValue('200000')
    expect(within(head('setaside')).getByRole('button', { name: 'Selected' })).toBeDisabled()
  })

  it('partner closed: "not open to you yet" with the tap, no choose button, no numbers', () => {
    setup(fx('funding_compare'))
    const partner = head('partner')
    expect(within(partner).getByText('Not open to you yet')).toBeInTheDocument()
    expect(within(partner).getByText(/tap “A local partner\?”/)).toBeInTheDocument()
    expect(within(partner).queryByRole('button')).toBeNull()
    const cells = within(row('open_likely')).getAllByRole('cell')
    expect(cells[2]).toHaveTextContent('—')
  })

  it('"Choose this funding" emits that column\'s toggle_option actions, the typed savings and the slider share', async () => {
    const { emit, user } = setup(fx('funding_compare'))
    await user.click(within(head('savings')).getByRole('button', { name: 'Choose this funding' }))
    expect(emit).toHaveBeenCalledWith('toggle_option', {
      value: 'savings',
      data: {
        column: 'savings',
        options: [
          { id: 'own_savings', on: true, amount: '200000' },
          { id: 'partner_equity', on: false },
        ],
        share: 0.4,
      },
      label: 'Choose this funding: Set-aside + your savings',
    })
  })

  it('editing the savings previews the column; a bad amount blocks choosing', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const base = fx('funding_compare')
    const p = base.payload as { columns: CompareColumn[] }
    const preview = vi.fn(async () => ({
      columns: p.columns,
      figures: {},
      display: { 'funding.compare.savings.open_likely': 'preview month 12' },
    }))
    const { emit } = setup(base, { env: { previewCompare: preview } })
    const input = screen.getByLabelText('Extra savings for Set-aside + your savings, in RMB')
    fireEvent.change(input, { target: { value: '450000' } })
    await act(async () => vi.advanceTimersByTime(350))
    expect(preview).toHaveBeenCalledWith('/api/preview/compare', '450000', expect.any(AbortSignal))
    expect(await screen.findByText('preview month 12')).toBeInTheDocument()
    fireEvent.change(input, { target: { value: '-5' } })
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('Enter a whole amount from 0 to RMB 2m')).toBeInTheDocument()
    expect(within(head('savings')).getByRole('button', { name: 'Choose this funding' })).toBeDisabled()
    await act(async () => vi.advanceTimersByTime(350))
    expect(preview).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
    expect(emit).not.toHaveBeenCalled()
  })

  it('partner open: profit share shown, its pros and cons from the ranking words and the catalogue', async () => {
    const { emit, user } = setup(fx('funding_compare.partner'))
    expect(within(row('profit_share')).getByText('30%')).toBeInTheDocument()
    expect(within(row('ownership')).getByText('70%')).toBeInTheDocument()
    expect(within(head('savings')).getByRole('button', { name: 'Selected' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByRole('button', { name: 'Pros and cons of Set-aside + a local partner' }))
    const pc = document.querySelector('[data-pros-cons="partner"]') as HTMLElement
    for (const w of ['Fastest', 'Costs a share of the profit', 'Gives up ownership']) expect(within(pc).getByText(w)).toBeInTheDocument()
    expect(within(pc).getByText('A share of the profit')).toBeInTheDocument() // the catalogue's cost
    await user.click(within(head('partner')).getByRole('button', { name: 'Choose this funding' }))
    expect(emit).toHaveBeenCalledWith('toggle_option', {
      value: 'partner',
      data: {
        column: 'partner',
        options: [
          { id: 'own_savings', on: false },
          { id: 'partner_equity', on: true },
        ],
        share: 0.4,
      },
      label: 'Choose this funding: Set-aside + a local partner',
    })
  })

  it('Chinese: the chrome and the word labels are in Chinese', async () => {
    await i18n.changeLanguage('zh')
    const { user } = setup(fx('funding_compare'))
    expect(screen.getByRole('group', { name: '比较资金方案' })).toBeInTheDocument()
    expect(within(head('savings')).getByRole('button', { name: '选择此方案' })).toBeInTheDocument()
    expect(within(head('partner')).getByText('暂不适用于您')).toBeInTheDocument()
    expect(within(row('ownership')).getByText('保留的股权')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Set-aside only的优点与不足' }))
    expect(screen.getByText('开业最晚')).toBeInTheDocument()
    await i18n.changeLanguage('en')
  })

  it('narrow container: the plans stack as cards with the same rows, and choosing still works', async () => {
    const rect = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 300 } as DOMRect)
    const { emit, user } = setup(fx('funding_compare.partner'))
    expect(screen.queryByRole('table')).toBeNull()
    const card = document.querySelector('li[data-column="partner"]') as HTMLElement
    expect(within(card).getByText("Partner's share of the profit")).toBeInTheDocument()
    expect(within(card).getByText('30%')).toBeInTheDocument()
    const setaside = document.querySelector('li[data-column="setaside"]') as HTMLElement
    expect(within(setaside).queryByText("Partner's share of the profit")).toBeNull()
    await user.click(within(setaside).getByRole('button', { name: 'Choose this funding' }))
    expect(emit).toHaveBeenCalledWith('toggle_option', expect.objectContaining({ value: 'setaside' }))
    rect.mockRestore()
  })

  it('empty, read-only and disabled states', () => {
    const empty = fx('funding_compare')
    ;(empty.payload as { columns: unknown[] }).columns = []
    const { unmount } = setup(empty)
    expect(screen.getByText('No plans to compare yet.')).toBeInTheDocument()
    unmount()
    const ro = setup(fx('funding_compare'), { readOnly: true })
    expect(screen.queryByRole('button', { name: 'Choose this funding' })).toBeNull()
    ro.unmount()
    setup(fx('funding_compare'), { disabled: true })
    expect(screen.getByRole('button', { name: 'Choose this funding' })).toBeDisabled()
  })
})
