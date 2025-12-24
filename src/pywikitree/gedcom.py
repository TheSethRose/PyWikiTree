from __future__ import annotations

import datetime
from typing import Any, Mapping, Sequence


class GedcomExporter:
    """Utility to convert WikiTree person data into GEDCOM 5.5.1 format."""

    def __init__(self, people: Sequence[Mapping[str, Any]]) -> None:
        self.people = {str(p.get("Id")): p for p in people if p.get("Id")}
        self.families: dict[str, dict[str, Any]] = {}

    def _format_date(self, date_str: str | None) -> str:
        """Convert YYYY-MM-DD to GEDCOM DATE format (e.g., 30 NOV 1835)."""
        if not date_str or date_str == "0000-00-00" or date_str == "0000":
            return ""
        
        try:
            # Handle partial dates like "1835-00-00" or "1835-11-00"
            parts = date_str.split("-")
            year = parts[0]
            month = "00"
            day = "00"
            
            if len(parts) > 1:
                month = parts[1]
            if len(parts) > 2:
                day = parts[2]
                
            months = [
                "", "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"
            ]
            
            m_idx = int(month)
            d_val = int(day)
            
            res = []
            if 1 <= d_val <= 31:
                res.append(str(d_val))
            if 1 <= m_idx <= 12:
                res.append(months[m_idx])
            if year != "0000":
                res.append(year)
                
            return " ".join(res)
        except (ValueError, IndexError):
            return date_str

    def _generate_families(self) -> None:
        """Group people into families based on Father/Mother IDs."""
        for person_id, person in self.people.items():
            father_id = str(person.get("Father", "0"))
            mother_id = str(person.get("Mother", "0"))
            
            if father_id == "0" and mother_id == "0":
                continue
                
            # Create a unique key for this parental pair
            fam_key = f"F_{father_id}_{mother_id}"
            if fam_key not in self.families:
                self.families[fam_key] = {
                    "HUSB": father_id if father_id != "0" else None,
                    "WIFE": mother_id if mother_id != "0" else None,
                    "CHIL": []
                }
            self.families[fam_key]["CHIL"].append(person_id)

    def export(self) -> str:
        """Generate the full GEDCOM string."""
        self._generate_families()
        
        lines = [
            "0 HEAD",
            "1 SOUR WikiTree",
            "1 GEDC",
            "2 VERS 5.5.1",
            "2 FORM LINEAGE-LINKED",
            "1 CHAR UTF-8",
            f"1 DATE {datetime.datetime.now().strftime('%d %b %Y').upper()}",
        ]
        
        # Individuals
        for p_id, p in self.people.items():
            lines.append(f"0 @I{p_id}@ INDI")
            
            first = p.get("FirstName", p.get("RealName", ""))
            last = p.get("LastNameAtBirth", "")
            lines.append(f"1 NAME {first} /{last}/")
            
            gender = p.get("Gender", "")
            if gender:
                lines.append(f"1 SEX {gender[0].upper()}")
                
            # Birth
            birth_date = self._format_date(p.get("BirthDate"))
            birth_plac = p.get("BirthLocation")
            if birth_date or birth_plac:
                lines.append("1 BIRT")
                if birth_date:
                    lines.append(f"2 DATE {birth_date}")
                if birth_plac:
                    lines.append(f"2 PLAC {birth_plac}")
                    
            # Death
            death_date = self._format_date(p.get("DeathDate"))
            death_plac = p.get("DeathLocation")
            if death_date or death_plac:
                lines.append("1 DEAT")
                if death_date:
                    lines.append(f"2 DATE {death_date}")
                if death_plac:
                    lines.append(f"2 PLAC {death_plac}")
            
            # Link to family where they are a child
            father_id = str(p.get("Father", "0"))
            mother_id = str(p.get("Mother", "0"))
            if father_id != "0" or mother_id != "0":
                lines.append(f"1 FAMC @F_{father_id}_{mother_id}@")

            # Note with WikiTree ID
            wt_name = p.get("Name")
            if wt_name:
                lines.append(f"1 NOTE WikiTree ID: {wt_name}")

        # Families
        for fam_id, fam in self.families.items():
            lines.append(f"0 @{fam_id}@ FAM")
            if fam["HUSB"] and fam["HUSB"] in self.people:
                lines.append(f"1 HUSB @I{fam['HUSB']}@")
            if fam["WIFE"] and fam["WIFE"] in self.people:
                lines.append(f"1 WIFE @I{fam['WIFE']}@")
            for child_id in fam["CHIL"]:
                lines.append(f"1 CHIL @I{child_id}@")
                
        lines.append("0 TRLR")
        return "\n".join(lines)
