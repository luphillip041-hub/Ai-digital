import Anthropic from '@anthropic-ai/sdk';

const client = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY,
});

export async function runMarketResearchAgent(topic: string): Promise<string> {
  const systemPrompt = `You are an expert market research analyst and business strategist.
Your job is to analyze markets, identify profitable niches, and provide actionable intelligence.
Always respond with structured JSON data following the exact schema requested.
Be data-driven, specific, and realistic in your assessments.`;

  const userPrompt = `Research this market/niche: "${topic}"

Analyze and return a JSON object with this exact structure:
{
  "niche": "specific niche name",
  "marketSize": "estimated market size in USD (e.g. $2.4B globally)",
  "competition": "low|medium|high",
  "revenueModel": "primary revenue model (e.g. SaaS subscription, affiliate, ads)",
  "startupCost": "realistic startup cost range (e.g. $500-$2,000)",
  "timeToRevenue": "estimated time to first revenue (e.g. 2-4 months)",
  "score": 85,
  "opportunities": ["opportunity 1", "opportunity 2", "opportunity 3"],
  "risks": ["risk 1", "risk 2"],
  "actionPlan": ["step 1", "step 2", "step 3", "step 4", "step 5"],
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "summary": "2-3 sentence executive summary"
}

The score (0-100) represents overall opportunity score based on: market size, competition level, revenue potential, and ease of entry.
Be specific and actionable. Focus on digital/online business opportunities.`;

  const message = await client.messages.create({
    model: 'claude-sonnet-4-6',
    max_tokens: 1024,
    messages: [{ role: 'user', content: userPrompt }],
    system: systemPrompt,
  });

  const content = message.content[0];
  if (content.type !== 'text') throw new Error('Unexpected response type');
  return content.text;
}

export async function runContentGenerationAgent(
  topic: string,
  type: string,
  keywords: string[]
): Promise<string> {
  const systemPrompt = `You are an expert SEO copywriter and content strategist.
You create high-converting, SEO-optimized content that drives organic traffic and conversions.
Always respond with structured JSON following the exact schema requested.`;

  const typeInstructions: Record<string, string> = {
    blog: 'a comprehensive 800-1200 word blog post with H2/H3 headers using markdown',
    landing: 'a persuasive landing page with hero, benefits, features, social proof, and CTA sections',
    email: 'an email sequence of 3 emails: welcome, value, and conversion',
    social: '5 social media posts optimized for engagement (Twitter/LinkedIn/Instagram)',
    ad: '3 ad variations: headline, body, and CTA for Google/Meta ads',
  };

  const instruction = typeInstructions[type] || typeInstructions.blog;

  const message = await client.messages.create({
    model: 'claude-sonnet-4-6',
    max_tokens: 2048,
    messages: [{
      role: 'user',
      content: `Create ${instruction} about: "${topic}"

Target keywords to include naturally: ${keywords.join(', ')}

Return JSON with this structure:
{
  "title": "compelling title",
  "content": "the full content here",
  "metaDescription": "150-char SEO meta description",
  "seoScore": 88,
  "wordCount": 950,
  "readingTime": "4 min read",
  "cta": "primary call to action"
}`
    }],
    system: systemPrompt,
  });

  const content = message.content[0];
  if (content.type !== 'text') throw new Error('Unexpected response type');
  return content.text;
}

export async function runBusinessValidationAgent(idea: string): Promise<string> {
  const systemPrompt = `You are a seasoned startup advisor and business analyst with expertise in evaluating business ideas.
You provide honest, data-backed assessments to help entrepreneurs succeed.
Return structured JSON analysis.`;

  const message = await client.messages.create({
    model: 'claude-sonnet-4-6',
    max_tokens: 1500,
    messages: [{
      role: 'user',
      content: `Validate this business idea: "${idea}"

Provide a comprehensive validation in this JSON format:
{
  "name": "business name suggestion",
  "description": "refined business description",
  "targetMarket": "specific target customer profile",
  "revenueStreams": ["stream 1", "stream 2", "stream 3"],
  "validationScore": 72,
  "strengths": ["strength 1", "strength 2", "strength 3"],
  "weaknesses": ["weakness 1", "weakness 2"],
  "opportunities": ["opportunity 1", "opportunity 2"],
  "threats": ["threat 1", "threat 2"],
  "revenueProjection": {
    "month3": "$500-$1,500",
    "month6": "$2,000-$5,000",
    "month12": "$8,000-$20,000"
  },
  "mvpFeatures": ["feature 1", "feature 2", "feature 3"],
  "feedback": "detailed honest feedback paragraph",
  "nextSteps": ["step 1", "step 2", "step 3", "step 4"]
}`
    }],
    system: systemPrompt,
  });

  const content = message.content[0];
  if (content.type !== 'text') throw new Error('Unexpected response type');
  return content.text;
}

export async function runCompetitorAnalysisAgent(niche: string): Promise<string> {
  const systemPrompt = `You are a competitive intelligence expert.
Analyze competitive landscapes and identify market gaps and opportunities.
Return structured JSON with actionable competitor insights.`;

  const message = await client.messages.create({
    model: 'claude-sonnet-4-6',
    max_tokens: 1500,
    messages: [{
      role: 'user',
      content: `Analyze the competitive landscape for: "${niche}"

Return JSON with this structure:
{
  "marketOverview": "2-3 sentence market overview",
  "topCompetitors": [
    {
      "name": "Competitor Name",
      "estimatedRevenue": "$X/year",
      "pricing": "$X/month",
      "strengths": ["s1", "s2"],
      "weaknesses": ["w1", "w2"],
      "marketShare": "~X%"
    }
  ],
  "marketGaps": ["gap 1", "gap 2", "gap 3"],
  "differentiationStrategies": ["strategy 1", "strategy 2", "strategy 3"],
  "entryBarriers": ["barrier 1", "barrier 2"],
  "pricingInsights": "pricing strategy recommendation",
  "winningStrategy": "3-4 sentence winning strategy to enter this market"
}`
    }],
    system: systemPrompt,
  });

  const content = message.content[0];
  if (content.type !== 'text') throw new Error('Unexpected response type');
  return content.text;
}

export async function runTrendResearchAgent(industry: string): Promise<string> {
  const systemPrompt = `You are a trend analyst and futurist specializing in digital business opportunities.
Identify emerging trends and translate them into actionable business opportunities.`;

  const message = await client.messages.create({
    model: 'claude-sonnet-4-6',
    max_tokens: 1200,
    messages: [{
      role: 'user',
      content: `Identify top emerging trends and opportunities in: "${industry}"

Return JSON:
{
  "industry": "${industry}",
  "trendScore": 85,
  "emergingTrends": [
    {
      "trend": "trend name",
      "description": "what it is and why it matters",
      "opportunitySize": "market opportunity estimate",
      "timeframe": "when this becomes mainstream",
      "businessIdeas": ["idea 1", "idea 2"]
    }
  ],
  "hotKeywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "investmentAreas": ["area 1", "area 2", "area 3"],
  "summary": "executive summary of the trend landscape"
}`
    }],
    system: systemPrompt,
  });

  const content = message.content[0];
  if (content.type !== 'text') throw new Error('Unexpected response type');
  return content.text;
}
