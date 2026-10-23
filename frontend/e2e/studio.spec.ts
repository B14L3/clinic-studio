import { expect, test, type Page } from "@playwright/test";

const MOCK_ANALYSIS = {
  visual_summary_hebrew: "הסרטון מציג טיפול פנים דינמי עם חיתוכים מהירים ופרטים אסתטיים.",
  segments: [
    { start_time: 1.0, end_time: 2.5, action_description: "מריחת מסכה" },
    { start_time: 4.0, end_time: 6.0, action_description: "מכשיר על הלחי" },
  ],
};

const MOCK_GENERATE = {
  status: "success",
  video_path: "D:/ClinicStudio/outputs/reel_test.mp4",
  filename: "reel_test.mp4",
  video_url: "/outputs/reel_test.mp4",
  duration: 3.5,
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

async function mockRawClips(page: Page) {
  await page.route("**/api/raw-clips", async (route) => {
    await route.fulfill({ json: [] });
  });
}

async function analyzeFootage(page: Page) {
  await page.goto("/");
  await page.getByTestId("toggle-manual-source").click();
  await page.getByTestId("source-path-input").fill("references/treatment_flow/clip.mp4");
  await page.getByTestId("analyze-button").click();
  await expect(page.getByTestId("visual-summary")).toBeVisible();
}

test("initial state displays source input and analyze button", async ({ page }) => {
  await mockRawClips(page);
  await page.goto("/");

  await expect(page.getByTestId("upload-button")).toBeVisible();
  await expect(page.getByTestId("toggle-manual-source")).toBeVisible();

  await expect(page.getByTestId("source-path-input")).toHaveCount(0);
  await page.getByTestId("toggle-manual-source").click();
  await expect(page.getByTestId("source-path-input")).toBeVisible();

  await expect(page.getByTestId("analyze-button")).toBeVisible();
  await expect(page.getByTestId("visual-summary")).toHaveCount(0);
  await expect(page.getByTestId("segment-start-0")).toHaveCount(0);
});

test("analyzing footage renders the Hebrew summary and editable segment fields", async ({ page }) => {
  await mockRawClips(page);
  await mockAnalyze(page);
  await analyzeFootage(page);

  const summary = page.getByTestId("visual-summary");
  await expect(summary).toHaveAttribute("dir", "rtl");
  await expect(summary).toContainText(MOCK_ANALYSIS.visual_summary_hebrew);

  await expect(page.getByTestId("segment-start-0")).toHaveValue("1");
  await expect(page.getByTestId("segment-end-0")).toHaveValue("2.5");
  await expect(page.getByTestId("segment-action-0")).toHaveValue("מריחת מסכה");
  await expect(page.getByTestId("segment-start-1")).toHaveValue("4");
  await expect(page.getByTestId("segment-delete-0")).toBeVisible();
});

test("editing a segment start time is sent in the generate payload", async ({ page }) => {
  await mockRawClips(page);
  await mockAnalyze(page);

  let generateRequestBody:
    | { segments?: { start_time: number; end_time: number; action_description: string }[]; visual_summary?: string }
    | undefined;
  await page.route("**/api/reels/generate", async (route) => {
    generateRequestBody = route.request().postDataJSON();
    await route.fulfill({ json: MOCK_GENERATE });
  });

  await analyzeFootage(page);
  await page.getByTestId("segment-start-0").fill("1.5");
  await page.getByTestId("treatment-input").fill("טיפול מזותרפיה");
  await page.getByTestId("generate-button").click();

  await expect(page.getByTestId("result-section")).toBeVisible();
  expect(generateRequestBody?.segments?.[0]?.start_time).toBe(1.5);
  expect(generateRequestBody?.segments?.[1]?.action_description).toBe("מכשיר על הלחי");
  expect(generateRequestBody?.visual_summary).toBe(MOCK_ANALYSIS.visual_summary_hebrew);
});

test("selecting a video file uploads it and automatically triggers analysis", async ({ page }) => {
  await mockRawClips(page);
  await mockAnalyze(page);

  const mockUploadResponse = {
    filename: "20261008_230000_abcd1234_clip.mp4",
    file_path: "raw_clips/20261008_230000_abcd1234_clip.mp4",
    size_mb: 4.2,
  };
  let uploadReceived = false;
  await page.route("**/api/upload", async (route) => {
    uploadReceived = true;
    await route.fulfill({ json: mockUploadResponse });
  });

  await page.goto("/");
  await page.getByTestId("file-input").setInputFiles({
    name: "clip.mp4",
    mimeType: "video/mp4",
    buffer: Buffer.from("fake-mp4-bytes-for-testing"),
  });

  await expect(page.getByTestId("visual-summary")).toBeVisible();
  await expect(page.getByTestId("segment-action-0")).toHaveValue("מריחת מסכה");
  expect(uploadReceived).toBe(true);
  await expect(page.getByText(mockUploadResponse.file_path)).toBeVisible();
});
