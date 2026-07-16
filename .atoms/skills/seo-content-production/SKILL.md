---
name: seo-content-production
description: "Generate Sarah's SEO content package after plan approval: page matrix, long-form markdown articles, hero/social image requirements, and frontmatter metadata for downstream embedding. Use when Sarah is producing SEO pages rather than only auditing, scanning, or handing off."
alwaysApply: true
roles:
  - Sarah
---

Use this skill whenever Sarah is generating SEO page plans or approved SEO markdown files.

What this skill owns:
- The page-matrix generation shape and output contract
- The long-form article generation template
- Frontmatter requirements needed for downstream embedding
- Single-image usage in markdown content and social metadata

## Step 1: Analyze project features and identify core keywords
- Based on project scan findings, determine 5-10 primary keywords
- Consider: product type, main features, target audience, pain points solved
- Think about what users would search for

## Step 2: Research and generate SEO outline

Before generating the outline, use WebSearchEngine to research (limit to 1 searches total across all queries):
1. Search for current SEO trends and best practices related to your target keywords
2. Research competitor content strategies and popular search queries in the domain
3. Identify trending topics and user pain points that align with the product features
4. Gather insights on content gaps and opportunities

WebSearchEngine usage:
```
<WebSearchEngine.run>
<query>[your search query combining product type + keywords + "SEO strategy" or "content ideas"]</query>
<flag>deep search</flag>
</WebSearchEngine.run>
```

After research, call `SEOSpecialist.generate_seo_outline`:
- Provide: topic (product description) and keywords (comma-separated list from step 1)
- Default: 20 pages across categories (Core Features, Use Cases, Comparisons, Pain Points, Education, FAQ)
- Each page includes: title, URL path, keywords, content outline
- Matrix is stored in memory automatically (self.seo_matrix)

## Step 3: Get user approval
Use `SEOSpecialist.draft_plan` to present plan to user:
- Format: Numbered list "1. Page Title A\n2. Page Title B\n..."
- Wait for user response (approve_all, approve with selections, or update)
- If UPDATE: Re-run `SEOSpecialist.generate_seo_outline` with adjusted parameters, then call `SEOSpecialist.draft_plan` again

## Step 4: Locate frontend project root
Before generating any files, locate the frontend project root (directory containing package.json):
1. Use Editor.find_file to search for package.json files
2. If multiple results, choose the most likely frontend root, preferring paths like:
   - ./app/frontend/package.json
   - ./shadcn-ui/package.json
   - If none match, choose the FIRST path

## Step 5: Generate markdown files and images
After receiving APPROVE/APPROVE_ALL from draft_plan, call `SEOSpecialist.generate_markdown_batch`:
- This tool handles everything: image generation, markdown content creation, and file writing
- It uses project_context and seo_matrix to ensure internal links, theme awareness, and accurate project references

Reference files:
- For page-matrix generation, read [references/outline-prompt.txt](references/outline-prompt.txt).
- For article generation, read [references/markdown-prompt.txt](references/markdown-prompt.txt).

Output expectations:
- Markdown files live under `seo/content/`.
- Frontmatter must stay stable and machine-readable for downstream embedding.
- By default, each article generates one image and reuses it for the hero image, `og_image`, and `twitter_image`.
- `og_image` and `twitter_image` should use the fixed remote URL form `https://atoms.template.com/assets/<image-filename>`.
- Default `twitter_site` to `https://atoms.template.com/` and `twitter_creator` to `@atoms_dev` unless the project context clearly provides better official values.

## Step 6: Handoff

Handoff rules:
- Ask Alex to embed the SEO content from `seo/content/` into the project.
- Do not provide any blog integration path analysis, new-vs-old logic comparison, or implementation strategy for Alex.
- Keep the handoff minimal: Sarah only needs to remind Alex that the SEO articles should be embedded into the existing project.
- Tell Alex to place the Blog entry where it is most visible, preferably the homepage or main navigation.
- Sarah does not need to edit frontend integration code herself unless specifically assigned.

Final reply requirements:
- Summarize page count and output directory.
- Mention that each page includes a social sharing image suitable for Open Graph style previews.
- Include a simple handoff sentence reminding Mike to ask Alex to embed the SEO articles into the project.
