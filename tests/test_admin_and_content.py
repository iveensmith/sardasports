"""The administrator's area and the public content it feeds.

The rules under test are the ones that keep the site honest: a published pick is never edited or
deleted after its match has started, and a premium pick is hidden from non-members only until
kick-off.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.account import ROLE_ADMIN, AuditLog, EmailOutbox, User
from app.models.content import ManualPick
from app.services import auth_service
from app.services.auth_service import hash_password

PASSWORD = "correct-horse-battery"


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _fresh_limits():
    auth_service.reset_rate_limits()
    yield
    auth_service.reset_rate_limits()


def _make_user(db_session, email, role="member", verified=True):
    user = User(
        email=email,
        password_hash=hash_password(PASSWORD),
        role=role,
        email_verified_at=_now() if verified else None,
        over_18_confirmed_at=_now(),
    )
    db_session.add(user)
    db_session.commit()
    return user


def _headers(client, email):
    token = client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin(client, db_session):
    _make_user(db_session, "admin@example.com", ROLE_ADMIN)
    return _headers(client, "admin@example.com")


@pytest.fixture
def member(client, db_session):
    _make_user(db_session, "member@example.com")
    return _headers(client, "member@example.com")


def _pick_body(**over):
    body = {
        "sport": "football",
        "competition": "Premier League",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "kickoff": (_now() + timedelta(hours=5)).isoformat(),
        "market": "Total goals",
        "selection": "Over 2.5",
        "odds": 1.85,
        "confidence": 70,
        "rationale": "Both sides score freely.",
        "premium_only": False,
        "publish": True,
    }
    body.update(over)
    return body


# --- picks: the integrity rules -----------------------------------------------------------


def test_the_admin_can_publish_a_pick_and_the_public_sees_it(client, admin):
    created = client.post("/admin/picks", json=_pick_body(), headers=admin)

    assert created.status_code == 200
    listing = client.get("/content/picks").json()
    assert [p["selection"] for p in listing["picks"]] == ["Over 2.5"]
    assert listing["picks"][0]["locked"] is False


def test_a_pick_cannot_be_published_after_its_match_has_started(client, admin):
    started = (_now() - timedelta(minutes=10)).isoformat()

    response = client.post("/admin/picks", json=_pick_body(kickoff=started), headers=admin)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "already_started"


def test_a_draft_can_be_saved_for_a_match_and_published_before_kickoff(client, admin):
    draft = client.post("/admin/picks", json=_pick_body(publish=False), headers=admin).json()
    assert client.get("/content/picks").json()["picks"] == []  # a draft is not public

    pick_id = draft["pick"]["id"]
    published = client.post(f"/admin/picks/{pick_id}/publish", headers=admin)

    assert published.status_code == 200
    assert len(client.get("/content/picks").json()["picks"]) == 1


def test_a_pick_can_be_deleted_before_kickoff(client, admin, db_session):
    pick_id = client.post("/admin/picks", json=_pick_body(), headers=admin).json()["pick"]["id"]

    response = client.delete(f"/admin/picks/{pick_id}", headers=admin)

    assert response.status_code == 200
    assert db_session.query(ManualPick).count() == 0
    assert db_session.query(AuditLog).filter_by(action="pick.delete").count() == 1


def test_a_pick_cannot_be_deleted_once_its_match_has_started(client, admin, db_session):
    pick_id = client.post("/admin/picks", json=_pick_body(), headers=admin).json()["pick"]["id"]
    pick = db_session.get(ManualPick, pick_id)
    pick.kickoff = _now() - timedelta(minutes=30)  # the match is now under way
    db_session.commit()

    response = client.delete(f"/admin/picks/{pick_id}", headers=admin)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "locked_after_kickoff"
    assert db_session.query(ManualPick).count() == 1


def test_a_result_is_settled_after_kickoff_and_counted_in_the_record(client, admin, db_session):
    won = client.post("/admin/picks", json=_pick_body(), headers=admin).json()["pick"]["id"]
    lost = client.post("/admin/picks", json=_pick_body(selection="Under 1.5"), headers=admin)
    lost_id = lost.json()["pick"]["id"]
    for pick_id in (won, lost_id):
        row = db_session.get(ManualPick, pick_id)
        row.kickoff = _now() - timedelta(hours=3)
    db_session.commit()

    assert (
        client.post(f"/admin/picks/{won}/settle", json={"result": "won"}, headers=admin).status_code
        == 200
    )
    assert (
        client.post(
            f"/admin/picks/{lost_id}/settle", json={"result": "lost"}, headers=admin
        ).status_code
        == 200
    )

    record = client.get("/content/picks/record").json()
    assert (record["won"], record["lost"], record["settled"], record["win_rate"]) == (1, 1, 2, 50.0)


def test_a_pick_cannot_be_settled_before_the_match_starts(client, admin):
    pick_id = client.post("/admin/picks", json=_pick_body(), headers=admin).json()["pick"]["id"]

    response = client.post(f"/admin/picks/{pick_id}/settle", json={"result": "won"}, headers=admin)

    assert response.status_code == 400 and response.json()["detail"]["code"] == "not_started"


def test_a_settled_result_cannot_be_flipped_only_voided_with_a_reason(client, admin, db_session):
    pick_id = client.post("/admin/picks", json=_pick_body(), headers=admin).json()["pick"]["id"]
    db_session.get(ManualPick, pick_id).kickoff = _now() - timedelta(hours=3)
    db_session.commit()
    client.post(f"/admin/picks/{pick_id}/settle", json={"result": "lost"}, headers=admin)

    flip = client.post(f"/admin/picks/{pick_id}/settle", json={"result": "won"}, headers=admin)
    no_reason = client.post(
        f"/admin/picks/{pick_id}/settle", json={"result": "void"}, headers=admin
    )
    void = client.post(
        f"/admin/picks/{pick_id}/settle",
        json={"result": "void", "void_reason": "Match abandoned"},
        headers=admin,
    )

    assert flip.status_code == 400 and flip.json()["detail"]["code"] == "already_settled"
    assert no_reason.status_code == 400 and void.status_code == 200
    record = client.get("/content/picks/record").json()
    assert (record["lost"], record["void"]) == (0, 1)


def test_bad_pick_fields_are_refused(client, admin):
    assert (
        client.post("/admin/picks", json=_pick_body(sport="cricket"), headers=admin).status_code
        == 400
    )
    assert client.post("/admin/picks", json=_pick_body(odds=0.5), headers=admin).status_code == 400
    assert (
        client.post("/admin/picks", json=_pick_body(confidence=150), headers=admin).status_code
        == 400
    )
    assert (
        client.post("/admin/picks", json=_pick_body(selection=" "), headers=admin).status_code
        == 400
    )


# --- premium picks and posts --------------------------------------------------------------


def test_a_premium_pick_is_hidden_from_visitors_until_kickoff(client, admin, member, db_session):
    pick_id = client.post("/admin/picks", json=_pick_body(premium_only=True), headers=admin).json()[
        "pick"
    ]["id"]

    visitor = client.get("/content/picks").json()["picks"][0]
    non_member = client.get("/content/picks", headers=member).json()["picks"][0]

    assert visitor["locked"] is True
    assert visitor["selection"] is None and visitor["odds"] is None and visitor["rationale"] is None
    assert visitor["home_team"] == "Arsenal"  # the fixture itself is not secret
    assert non_member["locked"] is True

    # From kick-off it is visible to everyone, with the result to come: premium sells early
    # access, not a record that shows only the winners.
    db_session.get(ManualPick, pick_id).kickoff = _now() - timedelta(minutes=5)
    db_session.commit()
    after = client.get("/content/picks").json()["picks"][0]
    assert after["locked"] is False and after["selection"] == "Over 2.5"


def test_a_member_with_premium_sees_a_premium_pick_early(client, admin, member, db_session):
    client.post("/admin/picks", json=_pick_body(premium_only=True), headers=admin)
    user = db_session.query(User).filter_by(email="member@example.com").one()
    client.post(f"/admin/users/{user.id}/grant", json={"days": 30}, headers=admin)

    pick = client.get("/content/picks", headers=member).json()["picks"][0]

    assert pick["locked"] is False and pick["selection"] == "Over 2.5"


def test_a_premium_post_shows_its_body_only_to_premium_members(client, admin, member, db_session):
    created = client.post(
        "/admin/posts",
        json={
            "title": "Weekend preview",
            "body": "The detailed view.",
            "premium_only": True,
            "publish": True,
        },
        headers=admin,
    ).json()["post"]
    slug = created["slug"]

    visitor = client.get(f"/content/posts/{slug}").json()["post"]
    assert visitor["locked"] is True and visitor["body"] == "" and visitor["excerpt"]

    user = db_session.query(User).filter_by(email="member@example.com").one()
    client.post(f"/admin/users/{user.id}/grant", json={"days": 7}, headers=admin)
    unlocked = client.get(f"/content/posts/{slug}", headers=member).json()["post"]
    assert unlocked["locked"] is False and unlocked["body"] == "The detailed view."


# --- posts --------------------------------------------------------------------------------


def test_a_post_is_a_draft_until_published(client, admin):
    draft = client.post(
        "/admin/posts", json={"title": "Season outlook", "body": "Text."}, headers=admin
    ).json()["post"]

    assert client.get("/content/posts").json()["total"] == 0
    assert client.get(f"/content/posts/{draft['slug']}").status_code == 404

    client.put(
        f"/admin/posts/{draft['id']}",
        json={"title": "Season outlook", "body": "Text.", "publish": True},
        headers=admin,
    )
    assert client.get("/content/posts").json()["total"] == 1
    assert client.get(f"/content/posts/{draft['slug']}").status_code == 200


def test_post_slugs_are_unique_and_url_safe(client, admin):
    first = client.post(
        "/admin/posts", json={"title": "Big Match: Arsenal v Chelsea!"}, headers=admin
    )
    second = client.post(
        "/admin/posts", json={"title": "Big Match: Arsenal v Chelsea!"}, headers=admin
    )

    assert first.json()["post"]["slug"] == "big-match-arsenal-v-chelsea"
    assert second.json()["post"]["slug"] == "big-match-arsenal-v-chelsea-2"


def test_a_post_can_be_unpublished_and_deleted(client, admin):
    post = client.post(
        "/admin/posts", json={"title": "Hello", "body": "x", "publish": True}, headers=admin
    ).json()["post"]

    client.post(f"/admin/posts/{post['id']}/unpublish", headers=admin)
    assert client.get("/content/posts").json()["total"] == 0

    assert client.delete(f"/admin/posts/{post['id']}", headers=admin).status_code == 200
    assert client.get(f"/admin/posts/{post['id']}", headers=admin).status_code == 404


def test_a_post_needs_a_title(client, admin):
    response = client.post("/admin/posts", json={"title": "  ", "body": "x"}, headers=admin)
    assert response.status_code == 400 and response.json()["detail"]["code"] == "title_required"


# --- members and the audit trail ----------------------------------------------------------


def test_the_admin_can_list_grant_revoke_and_delete_members(client, admin, member, db_session):
    user = db_session.query(User).filter_by(email="member@example.com").one()

    listing = client.get("/admin/users?q=member", headers=admin).json()["users"]
    assert [u["email"] for u in listing] == ["member@example.com"]

    granted = client.post(f"/admin/users/{user.id}/grant", json={"days": 30}, headers=admin)
    assert granted.json()["entitlement"]["premium"] is True

    client.post(f"/admin/users/{user.id}/revoke", headers=admin)
    me = client.get("/auth/me", headers=member).json()
    assert me["entitlement"]["premium"] is False

    assert client.delete(f"/admin/users/{user.id}", headers=admin).status_code == 200
    db_session.expire_all()
    assert db_session.query(User).filter_by(email="member@example.com").count() == 0


def test_admin_actions_leave_an_audit_trail(client, admin, db_session):
    client.post(
        "/admin/posts", json={"title": "Audited", "body": "x", "publish": True}, headers=admin
    )
    client.post("/admin/picks", json=_pick_body(), headers=admin)

    actions = [a.action for a in db_session.query(AuditLog).order_by(AuditLog.id)]
    assert "post.publish" in actions and "pick.publish" in actions
    entries = client.get("/admin/audit", headers=admin).json()["entries"]
    assert len(entries) >= 2


def test_the_outbox_is_readable_by_the_admin(client, admin):
    client.post(
        "/auth/register",
        json={
            "email": "new@example.com",
            "password": PASSWORD,
            "over_18": True,
            "accept_terms": True,
        },
    )

    outbox = client.get("/admin/outbox", headers=admin).json()
    assert outbox["mail_configured"] is False
    assert any(m["to"] == "new@example.com" and "token=" in m["body"] for m in outbox["messages"])
    assert EmailOutbox  # the model is what is being read


def test_a_premium_posts_automatic_summary_never_copies_its_body(client, admin):
    post = client.post(
        "/admin/posts",
        json={
            "title": "Secret",
            "body": "The whole short analysis.",
            "premium_only": True,
            "publish": True,
        },
        headers=admin,
    ).json()["post"]

    assert "whole short analysis" not in post["excerpt"]
    visitor = client.get(f"/content/posts/{post['slug']}").json()["post"]
    assert visitor["locked"] and "whole short analysis" not in str(visitor)


# --- the rich-text blog editor ---------------------------------------------------------------


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    from app.services import media_service

    monkeypatch.setattr(media_service, "media_dir", lambda: tmp_path)
    return tmp_path


def _png(size=(40, 30), color=(200, 30, 30)) -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _post(client, admin, **over):
    body = {"title": "Preview", "body": "<p>Hello</p>", "publish": True}
    body.update(over)
    return client.post("/admin/posts", json=body, headers=admin)


def test_a_post_body_is_cleaned_before_it_is_stored(client, admin):
    dirty = (
        '<p onclick="steal()">Hi <b>there</b></p><script>alert(1)</script>'
        '<a href="javascript:alert(1)">x</a><img src="/media/a.png" onerror="alert(1)">'
        '<iframe src="https://evil.example"></iframe>'
    )
    post = _post(client, admin, body=dirty).json()["post"]

    assert "script" not in post["body"] and "onclick" not in post["body"]
    assert "javascript:" not in post["body"] and "onerror" not in post["body"]
    assert "iframe" not in post["body"]
    assert "<b>there</b>" in post["body"] and "<p>" in post["body"]
    stored = client.get(f"/admin/posts/{post['id']}", headers=admin).json()["post"]
    assert stored["body"] == post["body"] and stored["body_format"] == "html"


def test_the_automatic_summary_is_plain_text_from_the_body(client, admin):
    post = _post(client, admin, body="<h2>Heading</h2><p>First <b>point</b>.</p>").json()["post"]

    assert post["excerpt"] == "Heading First point."


def test_a_post_carries_a_category_and_tidy_tags(client, admin):
    post = _post(
        client,
        admin,
        category="Match previews",
        tags=["  Arsenal ", "arsenal", "Premier League", "", "<b>x</b>", "a" * 80],
    ).json()["post"]

    assert post["category"] == "Match previews"
    assert post["tags"][:2] == ["Arsenal", "Premier League"]
    assert len(post["tags"]) == len(set(t.lower() for t in post["tags"]))
    assert all(len(t) <= 30 and "<" not in t for t in post["tags"])


def test_a_category_must_come_from_the_list(client, admin):
    response = _post(client, admin, category="Made up")

    assert response.status_code == 400
    assert "Match previews" in client.get("/content/categories").json()["categories"]


def test_posts_can_be_listed_by_category(client, admin):
    _post(client, admin, title="One", category="News")
    _post(client, admin, title="Two", category="Match previews")

    listed = client.get("/content/posts", params={"category": "News"}).json()["posts"]

    assert [p["title"] for p in listed] == ["One"]


def test_an_uploaded_image_is_stored_and_served(client, admin, uploads):
    sent = client.post(
        "/admin/media", content=_png(), headers={**admin, "Content-Type": "image/png"}
    )
    assert sent.status_code == 200
    url = sent.json()["url"]
    assert url.startswith("/media/") and url.endswith(".png")

    post = _post(client, admin, featured_image=url).json()["post"]
    assert post["featured_image"] == url

    served = client.get(f"/content{url}")
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"
    assert "immutable" in served.headers["cache-control"]
    assert served.headers["x-content-type-options"] == "nosniff"


def test_a_file_that_is_not_an_image_is_refused(client, admin, uploads):
    response = client.post(
        "/admin/media",
        content=b"<script>alert(1)</script>",
        headers={**admin, "Content-Type": "image/png"},
    )

    assert response.status_code == 415
    assert list(uploads.iterdir()) == []


def test_only_an_administrator_can_upload(client, member, uploads):
    anonymous = client.post("/admin/media", content=_png(), headers={"Content-Type": "image/png"})
    as_member = client.post(
        "/admin/media", content=_png(), headers={**member, "Content-Type": "image/png"}
    )

    assert anonymous.status_code in (401, 403) and as_member.status_code == 403


def test_the_editors_image_dialog_gets_the_reply_it_expects(client, admin, uploads):
    boundary = "xBOUNDARYx"
    body = (
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="upload"; filename="pic.png"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode()
        + _png()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    response = client.post(
        "/admin/media?CKEditorFuncNum=3",
        content=body,
        headers={**admin, "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )

    assert response.status_code == 200
    assert "CKEDITOR.tools.callFunction(3," in response.text and "/media/" in response.text


def test_only_names_an_upload_could_have_are_served_or_attached(client, admin, uploads):
    assert client.get("/content/media/..%2Fsecret.png").status_code in (404, 422)
    assert client.get("/content/media/notanupload.png").status_code == 404
    assert _post(client, admin, featured_image="/media/../../etc/passwd").status_code == 400
