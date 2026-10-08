import { expect, test, type Page } from "@playwright/test";

const MOCK_ANALYSIS = {
  recommended_blueprint_id: 1,
  blueprint_name: "Ambient Treatment Flow (21 Micro-Cuts, Fast Paced)",
  confidence: 0.95,
  reasoning:
    "הסרטון מורכב מסדרת חיתוכים מהירים ודינמיים המציגים שלבים שונים של טיפול, ולכן מתאים לתבנית Ambient Treatment Flow.",
  blueprints: [
    {
      id: 1,
      name: "Ambient Treatment Flow (21 Micro-Cuts, Fast Paced)",
      category: "treatment_flow",
      duration: 34.0,
      segment_count: 21,
    },
    {
      id: 2,
      name: "Voiceover Explainer (12 Cuts, Structured Pacing)",
      category: "voiceover_flow",
      duration: 30.0,
      segment_count: 12,
    },
  ],
};

const MOCK_GENERATE = {
  status: "success",
  video_path: "D:/ClinicStudio/outputs/reel_test.mp4",
  filename: "reel_test.mp4",
  video_url: "/outputs/reel_test.mp4",
  duration: 12.5,
  copywriting: {
    on_screen_hook: "עור זוהר תוך דקות",
    caption: "טיפול מרענן שמעניק זוהר טבעי לעור.",
    call_to_action: "הזמינו תור עוד היום",
    hashtags: ["#קליניקה", "#טיפוח_עור"],
  },
};

async function mockAnalyze(page: Page) {
  await page.route("**/api/reels/analyze", async (route) => {
    await route.fulfill({ json: MOCK_ANALYSIS });
  });
}

async function analyzeFootage(page: Page) {
  await page.goto("/");
  await page.getByTestId("source-path-input").fill("references/treatment_flow/clip.mp4");
  await page.getByTestId("analyze-button").click();
  await expect(page.getByTestId("ai-recommendation-card")).toBeVisible();
}

test("initial state displays source input and analyze button", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByTestId("source-path-input")).toBeVisible();
  await expect(page.getByTestId("analyze-button")).toBeVisible();
  await expect(page.getByTestId("ai-recommendation-card")).toHaveCount(0);
});

test("analyzing footage surfaces the AI recommendation card with Hebrew reasoning", async ({ page }) => {
  await mockAnalyze(page);
  await analyzeFootage(page);

  const card = page.getByTestId("ai-recommendation-card");
  await expect(card).toContainText("AI Recommended");
  await expect(card).toContainText(MOCK_ANALYSIS.blueprint_name);
  await expect(card).toContainText("95%");

  const reasoning = page.getByTestId("ai-reasoning");
  await expect(reasoning).toHaveAttribute("dir", "rtl");
  await expect(reasoning).toContainText(MOCK_ANALYSIS.reasoning);
});

test("recommended blueprint is selected by default, and clicking another overrides it", async ({ page }) => {
  await mockAnalyze(page);
  await analyzeFootage(page);

  const recommendedCard = page.getByTestId("blueprint-card-1");
  const otherCard = page.getByTestId("blueprint-card-2");

  // Default: AI-recommended blueprint (id=1) is selected.
  await expect(recommendedCard).toHaveClass(/border-rose-400/);
  await expect(otherCard).not.toHaveClass(/border-rose-400/);

  // Override: clicking another blueprint selects it instead.
  await otherCard.click();
  await expect(otherCard).toHaveClass(/border-rose-400/);
  await expect(recommendedCard).not.toHaveClass(/border-rose-400/);
});

test("generate button sends the currently selected blueprint id in the request payload", async ({ page }) => {
  await mockAnalyze(page);

  let generateRequestBody: { blueprint_id?: number } | undefined;
  await page.route("**/api/reels/generate", async (route) => {
    generateRequestBody = route.request().postDataJSON();
    await route.fulfill({ json: MOCK_GENERATE });
  });

  await analyzeFootage(page);

  // Override the AI recommendation (id=1) with blueprint id=2 before generating.
  await page.getByTestId("blueprint-card-2").click();
  await page.getByTestId("treatment-input").fill("טיפול מזותרפיה");
  await page.getByTestId("generate-button").click();

  await expect(page.getByTestId("result-section")).toBeVisible();
  expect(generateRequestBody?.blueprint_id).toBe(2);
});
