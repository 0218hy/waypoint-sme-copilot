import Ajv2020 from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import { describe, expect, it } from 'vitest'
import widgetSchema from '@/contracts/widget.schema.json'
import eventSchema from '@/contracts/widget_event.schema.json'
import { fixtures } from '@/dev/fixtures'
import { ALL_WIDGET_TYPES } from '@/widgets/types'
import { widgetRenderers } from '@/widgets/registry'

const ajv = new Ajv2020({ allErrors: true, strict: false })
addFormats(ajv)
const validateWidget = ajv.compile(widgetSchema)
const validateEvent = ajv.compile(eventSchema)

describe('dev fixtures', () => {
  it.each(fixtures.map((f) => [f.name, f.widget] as const))('%s validates against widget.schema.json', (_name, widget) => {
    const ok = validateWidget(widget)
    expect(validateWidget.errors ?? []).toEqual([])
    expect(ok).toBe(true)
  })

  it('every figure id a payload references is in display', () => {
    for (const { name, widget } of fixtures) {
      for (const id of Object.keys(widget.figures ?? {})) {
        expect(widget.display?.[id], `${name}: ${id}`).toBeTypeOf('string')
      }
    }
  })

  it('covers every widget type in agent/widgets.py', () => {
    const covered = new Set(fixtures.map((f) => f.widget.payload.type))
    for (const t of ALL_WIDGET_TYPES) expect(covered.has(t), t).toBe(true)
  })

  it('the registry has exactly one renderer per widget type in the schema', () => {
    const schemaTypes = Object.keys((widgetSchema as { properties: { payload: { discriminator: { mapping: object } } } }).properties.payload.discriminator.mapping).sort()
    expect(widgetRenderers.map((r) => r.name).sort()).toEqual(schemaTypes)
    expect([...ALL_WIDGET_TYPES].sort()).toEqual(schemaTypes)
  })

  it('a sample event validates against widget_event.schema.json', () => {
    expect(validateEvent({ widget_id: 'w1', event: 'select_area', value: 'TAMPINES', data: { id: 'TAMPINES' } })).toBe(true)
    expect(validateEvent({ widget_id: 'w1', event: 'slider_preview', value: 0.4 })).toBe(false)
  })
})
