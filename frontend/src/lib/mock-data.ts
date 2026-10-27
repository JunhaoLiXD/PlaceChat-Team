import type { RoomSummary } from "@/lib/placechat-types";

export const MOCK_ROOMS: RoomSummary[] = [
  {
    id: "marston-science-library",
    name: "Marston Science Library",
    description:
      "Study spots, STEM questions, and late-night library check-ins.",
    category: "library",
    latitude: 29.6485,
    longitude: -82.3438,
    participant_count: 18,
  },
  {
    id: "library-west",
    name: "Library West",
    description:
      "Quiet floors, coffee breaks, and the pulse of University Avenue.",
    category: "library",
    latitude: 29.6516,
    longitude: -82.3426,
    participant_count: 24,
  },
  {
    id: "norman-hall",
    name: "Norman Hall",
    description:
      "A gathering place for education students and east-campus regulars.",
    category: "academic",
    latitude: 29.6462,
    longitude: -82.3387,
    participant_count: 7,
  },
  {
    id: "plaza-of-the-americas",
    name: "Plaza of the Americas",
    description:
      "What’s happening on the lawn, from Krishna lunch to club events.",
    category: "student life",
    latitude: 29.6502,
    longitude: -82.3419,
    participant_count: 31,
  },
  {
    id: "reitz-union",
    name: "Reitz Union",
    description:
      "Food, events, study sessions, and everything at the center of campus.",
    category: "student life",
    latitude: 29.6463,
    longitude: -82.3478,
    participant_count: 42,
  },
  {
    id: "southwest-rec",
    name: "Southwest Recreation Center",
    description:
      "Pickup games, workout tips, and finding your next gym partner.",
    category: "recreation",
    latitude: 29.638,
    longitude: -82.3687,
    participant_count: 15,
  },
  {
    id: "the-hub",
    name: "The Hub",
    description: "Quick campus questions and conversations between classes.",
    category: "dining",
    latitude: 29.648,
    longitude: -82.3456,
    participant_count: 12,
  },
  {
    id: "turlington-hall",
    name: "Turlington Hall",
    description:
      "Class talk, campus happenings, and the busiest brick path at UF.",
    category: "academic",
    latitude: 29.6497,
    longitude: -82.3437,
    participant_count: 27,
  },
];

export function findMockRoom(roomId: string) {
  return MOCK_ROOMS.find((room) => room.id === roomId);
}
