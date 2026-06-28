export type PartnerTier = "community" | "silver" | "gold" | "platinum"

export interface Partner {
  partner_id: string
  name: string
  email: string
  tier: string
  status: string
  revenue_share: number
  connectors_published: number
  rating: number
}

export interface TierDef {
  display_name: string
  min_connectors: number
  min_installs: number
  min_rating: number
  revenue_share: number
  benefits: string[]
}

export interface PartnerStats {
  total: number
  active: number
  by_tier: Record<string, number>
}

export interface ActivityEntry {
  partner_id: string
  activity_type: string
  description: string
  performed_at: string
}

export interface TierDefinition {
  name: PartnerTier
  display_name: string
  revenue_share: number
  min_connectors: number
  min_installs: number
  min_rating: number
  benefits: string[]
}

export interface PartnerBenefit {
  id: string
  partner_id: string
  benefit: string
  granted_at: string
  expires_at: string | null
  active: boolean
}

export interface PartnerActivity {
  id: string
  partner_id: string
  action: string
  details: string
  timestamp: string
}
