import { ShieldStar } from "@phosphor-icons/react";

import {
  CATASTROPHIC_HARD_BLOCKS,
  PERMISSION_PROFILE_DESCRIPTIONS,
  PERMISSION_PROFILE_LABELS,
  type PermissionProfile,
} from "./types";

interface Props {
  value: PermissionProfile;
  disabled?: boolean;
  onChange: (profile: PermissionProfile) => void;
}

const PROFILE_ORDER: PermissionProfile[] = [
  "request_approval",
  "smart_approval",
  "full_access",
  "custom",
];

export function PermissionProfilePicker({ value, disabled, onChange }: Props) {
  return (
    <div className="creative-profile-picker" role="radiogroup" aria-label="权限档位">
      {PROFILE_ORDER.map((profile) => {
        const checked = value === profile;
        return (
          <label
            key={profile}
            className={`creative-profile-option${checked ? " selected" : ""}${disabled ? " disabled" : ""}`}
          >
            <input
              type="radio"
              name="permission-profile"
              value={profile}
              checked={checked}
              disabled={disabled}
              onChange={() => onChange(profile)}
              aria-label={PERMISSION_PROFILE_LABELS[profile]}
            />
            <div className="creative-profile-info">
              <div className="creative-profile-name">
                <ShieldStar size={16} weight={checked ? "fill" : "regular"} />
                <strong>{PERMISSION_PROFILE_LABELS[profile]}</strong>
              </div>
              <p className="creative-profile-desc">
                {PERMISSION_PROFILE_DESCRIPTIONS[profile]}
              </p>
              {profile === "full_access" && checked && (
                <div className="creative-hard-blocks" aria-label="不可覆盖的灾难性硬限制">
                  <span className="creative-hard-blocks-title">仍会硬性阻止：</span>
                  <ul>
                    {CATASTROPHIC_HARD_BLOCKS.map((block) => (
                      <li key={block}>{block}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </label>
        );
      })}
    </div>
  );
}
