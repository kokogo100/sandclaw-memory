"""Real-world scenario tests -- 실제 사용자 시나리오 검증.

각 직업별로 실제 사용 흐름을 시뮬레이션합니다:
  1. 의사 -- 환자 기록 저장 → 재방문 시 기억
  2. 요리사 -- 레시피 저장 → "돼지불고기" 검색
  3. 회계사 -- 회사별 정보 저장 → 회사명으로 로드
  4. 웹 개발자 -- 프로젝트 기술 스택 기억
  5. 프로그램 개발자 -- 버그/결정 기록 → 나중에 "왜?" 검색
  6. 초보 개발자 -- 가장 단순한 사용법 (3줄)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sandclaw_memory import BrainMemory


# ─── Simulated AI tag extractor (real app would use OpenAI/Claude) ───
def simple_tag_extractor(content: str) -> list[str]:
    """Extracts keywords > 3 chars. Real app would call an AI API."""
    stop_words = {
        "this", "that", "with", "from", "have", "been", "were", "they",
        "will", "about", "after", "before", "should", "could", "would",
        "their", "there", "other", "which", "when", "what", "than",
        "very", "also", "just", "into", "over", "such", "some", "only",
    }
    words = content.lower().split()
    tags = []
    for w in words:
        clean = w.strip(".,!?;:()\"'·、。：")
        if len(clean) > 3 and clean not in stop_words:
            tags.append(clean)
    return list(dict.fromkeys(tags))[:7]  # deduplicate, max 7


# ═══════════════════════════════════════════════════════════
# Scenario 1: 의사 (Doctor)
# 환자 기록 저장 → 재방문 시 AI가 기억
# ═══════════════════════════════════════════════════════════
class TestDoctorScenario:

    def test_save_patient_record(self, tmp_path: Path) -> None:
        """의사가 환자 진료 기록을 저장한다."""
        with BrainMemory(
            db_path=str(tmp_path / "clinic"),
            tag_extractor=simple_tag_extractor,
        ) as brain:
            # 첫 방문: 환자 정보 저장
            brain.save(
                "Patient Kim, age 45. Diagnosed with hypertension. "
                "Prescribed Amlodipine 5mg daily. Blood pressure 150/95. "
                "Next visit in 2 weeks.",
                source="archive",
                tags=["patient-kim", "hypertension", "amlodipine"],
            )

            brain.save(
                "Patient Park, age 32. Mild cold symptoms. "
                "Prescribed rest and fluids. No medication needed.",
                source="archive",
                tags=["patient-park", "cold", "mild"],
            )

            # 2주 후: 환자 Kim 재방문 → AI가 기억해야 함
            results = brain.search("kim")
            assert len(results) >= 1
            assert "hypertension" in results[0].content.lower() or \
                   "Amlodipine" in results[0].content

            # Deep recall로 전체 맥락 가져오기
            context = brain.recall("Patient Kim follow-up visit", depth="deep")
            assert "Kim" in context or "kim" in context.lower()

    def test_patient_history_grows(self, tmp_path: Path) -> None:
        """같은 환자의 기록이 계속 쌓인다."""
        with BrainMemory(
            db_path=str(tmp_path / "clinic2"),
            tag_extractor=simple_tag_extractor,
        ) as brain:
            # Visit 1
            brain.save(
                "Patient Lee: first visit. Diabetes Type 2. HbA1c 7.2%. "
                "Started Metformin 500mg.",
                source="archive",
                tags=["patient-lee", "diabetes", "metformin"],
            )
            # Visit 2
            brain.save(
                "Patient Lee: follow-up. HbA1c improved to 6.8%. "
                "Continue Metformin. Add exercise recommendation.",
                source="archive",
                tags=["patient-lee", "diabetes", "improvement"],
            )
            # Visit 3
            brain.save(
                "Patient Lee: 3-month check. HbA1c 6.5%. Excellent progress. "
                "Reduce Metformin to 250mg.",
                source="archive",
                tags=["patient-lee", "diabetes", "dose-reduction"],
            )

            # 모든 기록 검색
            results = brain.search("patient-lee")
            assert len(results) == 3

            # 최신 상태 recall
            context = brain.recall("Patient Lee current status", depth="deep")
            assert isinstance(context, str)
            assert len(context) > 0


# ═══════════════════════════════════════════════════════════
# Scenario 2: 요리사 (Chef)
# 레시피 저장 → "돼지불고기" 검색
# ═══════════════════════════════════════════════════════════
class TestChefScenario:

    def test_save_and_find_recipe(self, tmp_path: Path) -> None:
        """요리사가 레시피를 저장하고 나중에 검색한다."""
        with BrainMemory(
            db_path=str(tmp_path / "kitchen"),
            tag_extractor=simple_tag_extractor,
        ) as brain:
            brain.save(
                "Bulgogi (돼지불고기): Thin sliced pork belly marinated in "
                "gochujang, soy sauce, garlic, sugar, sesame oil. "
                "Grill on high heat 3-4 minutes per side. "
                "Serve with lettuce wraps and ssamjang.",
                source="archive",
                tags=["bulgogi", "pork", "korean", "grill"],
            )

            brain.save(
                "Kimchi Jjigae: Aged kimchi, tofu, pork shoulder, "
                "gochugaru, garlic, anchovy stock. Boil 20 minutes. "
                "Best with day-old rice.",
                source="archive",
                tags=["kimchi-jjigae", "stew", "korean"],
            )

            brain.save(
                "Pasta Carbonara: Guanciale, eggs, pecorino, black pepper. "
                "Cook pasta al dente. Mix egg+cheese off heat. "
                "No cream! Traditional Roman style.",
                source="archive",
                tags=["carbonara", "pasta", "italian"],
            )

            # "돼지불고기" 검색
            results = brain.search("bulgogi")
            assert len(results) >= 1
            assert "pork" in results[0].content.lower() or "gochujang" in results[0].content.lower()

            # "한식" 검색 -> 여러 결과
            results_korean = brain.search("korean")
            assert len(results_korean) >= 2

            # 자연어 검색
            context = brain.recall("how to make grilled pork?", depth="deep")
            assert "pork" in context.lower() or "grill" in context.lower() or "bulgogi" in context.lower()

    def test_recipe_with_variations(self, tmp_path: Path) -> None:
        """같은 요리의 변형 레시피를 다르게 저장한다."""
        with BrainMemory(
            db_path=str(tmp_path / "kitchen2"),
            tag_extractor=simple_tag_extractor,
        ) as brain:
            brain.save(
                "Classic Ramen: Tonkotsu broth (12-hour pork bone simmer). "
                "Thin noodles, chashu, soft-boiled egg, nori, green onion.",
                source="archive",
                tags=["ramen", "tonkotsu", "japanese"],
            )

            brain.save(
                "Spicy Ramen variation: Add gochugaru and chili oil to "
                "tonkotsu base. Extra garlic. Top with bean sprouts.",
                source="archive",
                tags=["ramen", "spicy", "variation"],
            )

            results = brain.search("ramen")
            assert len(results) == 2


# ═══════════════════════════════════════════════════════════
# Scenario 3: 회계사 (Accountant)
# 회사별 정보 저장 → 회사명으로 로드
# ═══════════════════════════════════════════════════════════
class TestAccountantScenario:

    def test_save_company_info_and_retrieve(self, tmp_path: Path) -> None:
        """회계사가 고객사별 재무 정보를 저장하고 검색한다."""
        with BrainMemory(
            db_path=str(tmp_path / "accounting"),
            tag_extractor=simple_tag_extractor,
        ) as brain:
            brain.save(
                "ABC Corp: FY2025 revenue $12.5M, EBITDA $3.2M. "
                "Tax filing deadline April 15. Using QuickBooks. "
                "Contact: John Smith, CFO.",
                source="archive",
                tags=["abc-corp", "revenue", "tax", "fy2025"],
            )

            brain.save(
                "XYZ Ltd: FY2025 revenue $8.1M, net loss $200K. "
                "Needs cost restructuring. VAT issues pending. "
                "Contact: Jane Doe, CEO.",
                source="archive",
                tags=["xyz-ltd", "revenue", "loss", "vat"],
            )

            brain.save(
                "DEF Inc: Startup, pre-revenue. Burn rate $50K/month. "
                "12 months runway. Series A planned Q3 2026. "
                "Contact: Mike Lee, founder.",
                source="archive",
                tags=["def-inc", "startup", "fundraising"],
            )

            # 회사명으로 검색
            results = brain.search("abc-corp")
            assert len(results) >= 1
            assert "$12.5M" in results[0].content

            # 재무 이슈 검색
            results_loss = brain.search("loss")
            assert len(results_loss) >= 1
            assert "XYZ" in results_loss[0].content

            # 전체 고객 맥락
            context = brain.recall("which clients need attention?", depth="deep")
            assert isinstance(context, str)
            assert len(context) > 0

    def test_update_company_info(self, tmp_path: Path) -> None:
        """회사 정보가 업데이트되면 새 기록이 추가된다."""
        with BrainMemory(
            db_path=str(tmp_path / "accounting2"),
            tag_extractor=simple_tag_extractor,
        ) as brain:
            brain.save(
                "MNO Corp Q1 2026: Revenue $2.1M, on track.",
                source="archive",
                tags=["mno-corp", "q1-2026"],
            )
            brain.save(
                "MNO Corp Q2 2026: Revenue $2.8M, 33% growth. "
                "Exceeded targets. Bonus pool approved.",
                source="archive",
                tags=["mno-corp", "q2-2026", "growth"],
            )

            results = brain.search("mno-corp")
            assert len(results) == 2  # Both quarters preserved


# ═══════════════════════════════════════════════════════════
# Scenario 4: 웹 개발자 (Web Developer)
# 프로젝트 기술 스택 + 결정 기록
# ═══════════════════════════════════════════════════════════
class TestWebDeveloperScenario:

    def test_project_tech_stack_memory(self, tmp_path: Path) -> None:
        """웹 개발자가 프로젝트의 기술 결정을 기록한다."""
        with BrainMemory(
            db_path=str(tmp_path / "webdev"),
            tag_extractor=simple_tag_extractor,
        ) as brain:
            brain.save(
                "Project Falcon: React 19 + TypeScript frontend. "
                "Tailwind CSS for styling. Vite for bundling.",
                source="archive",
                tags=["falcon", "react", "typescript", "tailwind"],
            )

            brain.save(
                "Project Falcon backend: FastAPI + PostgreSQL. "
                "Redis for caching. Docker for deployment.",
                source="archive",
                tags=["falcon", "fastapi", "postgresql", "docker"],
            )

            brain.save(
                "Project Falcon decision: chose Supabase over Firebase "
                "because of PostgreSQL support and row-level security.",
                source="archive",
                tags=["falcon", "supabase", "decision"],
            )

            # "왜 Supabase?" 검색
            results = brain.search("supabase")
            assert len(results) >= 1
            assert "Firebase" in results[0].content or "PostgreSQL" in results[0].content

            # 기술 스택 전체 recall
            context = brain.recall("what is Project Falcon's tech stack?", depth="deep")
            assert "React" in context or "react" in context.lower() or "falcon" in context.lower()

    def test_bug_tracking_memory(self, tmp_path: Path) -> None:
        """버그와 해결 방법을 기록한다."""
        with BrainMemory(
            db_path=str(tmp_path / "webdev_bugs"),
            tag_extractor=simple_tag_extractor,
        ) as brain:
            brain.save(
                "Bug: CORS error on /api/auth endpoint. Fixed by adding "
                "allow_origins=['*'] in FastAPI middleware. Took 2 hours.",
                source="archive",
                tags=["bug", "cors", "fastapi", "auth"],
            )

            brain.save(
                "Bug: React hydration mismatch on SSR pages. Fixed by "
                "wrapping dynamic content in useEffect. Client-only rendering.",
                source="archive",
                tags=["bug", "react", "ssr", "hydration"],
            )

            # 나중에 같은 버그 발생 시 검색
            results = brain.search("cors")
            assert len(results) >= 1
            assert "allow_origins" in results[0].content


# ═══════════════════════════════════════════════════════════
# Scenario 5: 프로그램 개발자 (Software Engineer)
# 아키텍처 결정 + "왜?" 추적
# ═══════════════════════════════════════════════════════════
class TestSoftwareEngineerScenario:

    def test_architecture_decisions(self, tmp_path: Path) -> None:
        """아키텍처 결정의 이유를 기록하고 나중에 "왜?" 로 검색한다."""
        with BrainMemory(
            db_path=str(tmp_path / "swe"),
            tag_extractor=simple_tag_extractor,
        ) as brain:
            brain.save(
                "Architecture decision: Monorepo with Turborepo. "
                "Reason: shared types between frontend/backend, "
                "single CI pipeline, easier refactoring.",
                source="archive",
                tags=["architecture", "monorepo", "turborepo", "decision"],
            )

            brain.save(
                "Architecture decision: Event-driven with RabbitMQ. "
                "Reason: decouple payment service from order service. "
                "Kafka was considered but too complex for our scale.",
                source="archive",
                tags=["architecture", "rabbitmq", "event-driven", "decision"],
            )

            brain.save(
                "Architecture decision: SQLite for embedded storage. "
                "Reason: zero-dependency, single-file DB, perfect for "
                "desktop apps. PostgreSQL overkill for this use case.",
                source="archive",
                tags=["architecture", "sqlite", "decision"],
            )

            # "왜 monorepo?" 검색
            context = brain.recall("why did we choose monorepo?", depth="deep")
            assert "monorepo" in context.lower() or "Turborepo" in context

            # 모든 아키텍처 결정 검색
            results = brain.search("architecture")
            assert len(results) >= 3

    def test_code_review_notes(self, tmp_path: Path) -> None:
        """코드 리뷰 노트를 저장하고 검색한다."""
        with BrainMemory(
            db_path=str(tmp_path / "swe_review"),
            tag_extractor=simple_tag_extractor,
        ) as brain:
            brain.save(
                "Code review: avoid using any type in TypeScript. "
                "Use unknown instead and narrow with type guards.",
                source="archive",
                tags=["review", "typescript", "best-practice"],
            )

            results = brain.search("typescript")
            assert len(results) >= 1


# ═══════════════════════════════════════════════════════════
# Scenario 6: 초보 개발자 (Beginner)
# 가장 단순한 사용법
# ═══════════════════════════════════════════════════════════
class TestBeginnerScenario:

    def test_simplest_possible_usage(self, tmp_path: Path) -> None:
        """초보 개발자가 가장 쉽게 사용하는 방법 -- 3줄이면 충분."""
        # 이게 전부입니다! 3줄!
        with BrainMemory(
            db_path=str(tmp_path / "easy"),
            tag_extractor=simple_tag_extractor,
        ) as brain:
            brain.save("I like pizza and coding")
            result = brain.recall("what do I like?")
            assert isinstance(result, str)

    def test_beginner_save_and_search(self, tmp_path: Path) -> None:
        """초보가 저장하고 검색하는 기본 패턴."""
        with BrainMemory(
            db_path=str(tmp_path / "beginner"),
            tag_extractor=simple_tag_extractor,
        ) as brain:
            # 중요한 것은 source="archive" 로 영구 저장
            brain.save("My favorite color is blue", source="archive", tags=["preference"])
            brain.save("I am learning Python", source="archive", tags=["learning"])

            # 검색
            results = brain.search("python")
            assert len(results) >= 1

            # 전체 기억 recall
            context = brain.recall("tell me about myself", depth="deep")
            assert len(context) > 0

    def test_beginner_no_crash_on_empty(self, tmp_path: Path) -> None:
        """아무것도 저장 안 해도 검색이 크래시 나지 않는다."""
        with BrainMemory(
            db_path=str(tmp_path / "empty"),
            tag_extractor=simple_tag_extractor,
        ) as brain:
            # 빈 상태에서 recall -- 절대 크래시 안 됨
            result = brain.recall("anything")
            assert isinstance(result, str)

            # 빈 상태에서 search -- 빈 리스트 반환
            results = brain.search("nothing here")
            assert results == []

            # 빈 상태에서 stats -- 정상 작동
            stats = brain.get_stats()
            assert stats["archive"]["total_memories"] == 0

    def test_beginner_with_statement_auto_cleanup(self, tmp_path: Path) -> None:
        """with 문을 쓰면 자동으로 정리된다 -- close() 안 불러도 됨."""
        with BrainMemory(
            db_path=str(tmp_path / "auto"),
            tag_extractor=simple_tag_extractor,
        ) as brain:
            brain.save("test")
        # with 블록 나오면 자동 close -- 에러 없으면 성공!

    def test_beginner_korean_content(self, tmp_path: Path) -> None:
        """한국어 컨텐츠도 문제없이 저장/검색된다."""
        with BrainMemory(
            db_path=str(tmp_path / "korean"),
            tag_extractor=simple_tag_extractor,
        ) as brain:
            brain.save(
                "사용자는 파이썬과 리액트를 주로 사용합니다",
                source="archive",
                tags=["파이썬", "리액트"],
            )
            brain.save(
                "점심으로 김치찌개를 먹었다",
                source="archive",
                tags=["김치찌개", "점심"],
            )

            results = brain.search("파이썬")
            assert len(results) >= 1

            results_food = brain.search("김치찌개")
            assert len(results_food) >= 1

    def test_beginner_japanese_content(self, tmp_path: Path) -> None:
        """日本語コンテンツも問題なく保存/検索される。"""
        with BrainMemory(
            db_path=str(tmp_path / "japanese"),
            tag_extractor=simple_tag_extractor,
        ) as brain:
            brain.save(
                "ユーザーはPythonとReactを使っています",
                source="archive",
                tags=["python", "react", "日本語"],
            )

            results = brain.search("python")
            assert len(results) >= 1
