from pymongo.database import Database
from typing import List, Optional
from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError, PyMongoError
from fastapi import HTTPException, status

from app.models.skill import Skill

class SkillService:
    @staticmethod
    def get_skills(
        db: Database,
        category: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> List[Skill]:
        """
        Fetch skills. If user_id is provided, returns that user's skills.
        Optionally filters by category.
        """
        query = {}

        if user_id:
            try:
                user_obj_id = ObjectId(user_id)
            except InvalidId:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid user ID format"
                )

            user = db["users"].find_one({"_id": user_obj_id})
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )

            user_skill_ids = user.get("skills", [])
            if not user_skill_ids:
                return []

            skill_obj_ids = [
                ObjectId(s_id) for s_id in user_skill_ids if ObjectId.is_valid(s_id)
            ]
            query["_id"] = {"$in": skill_obj_ids}

        if category:
            query["category"] = category

        skills_cursor = db["skills"].find(query)

        result = []
        for doc in skills_cursor:
            doc["_id"] = str(doc["_id"])
            result.append(Skill(**doc))

        return result

    @staticmethod
    def create_skill(db: Database, skill: Skill):
        """
        Create a new skill in the master skills collection.
        """
        skill_dict = skill.model_dump(by_alias=True, exclude_none=True)
        if "_id" in skill_dict and skill_dict["_id"] is None:
            del skill_dict["_id"]

        try:
            res = db["skills"].insert_one(skill_dict)
            if not res.acknowledged or not res.inserted_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create skill record."
                )
            return {
                "skill_id": str(res.inserted_id),
                "detail": "Skill inserted successfully!"
            }
        except DuplicateKeyError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This skill already exists"
            )
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while saving skill."
            )

    