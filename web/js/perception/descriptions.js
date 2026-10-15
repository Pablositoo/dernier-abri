// Ce que les « capteurs » voient de chaque silhouette : description et réaction à la sommation (FR + EN).
// Ces textes sont la seule chose que JEV reçoit (il ne voit jamais l'image ni la nature réelle).

export const DESC_I18N = {
  fr: {
    zombie: ["démarche lente et saccadée, grogne, bras tendus", "peau grise, mâchoire pendante, avance sans s'arrêter",
             "trébuche, ne cligne pas des yeux, gémissement continu"],
    humain: ["court vers l'abri en criant « aidez-moi ! »", "fait de grands signes avec les bras, porte un sac à dos",
             "court en zigzag, appelle ses amis par leur prénom"],
    blesse_zombie: ["boite, ensanglanté, ne répond pas quand on l'appelle", "ensanglanté, tête penchée, avance en ligne droite sans parler"],
    blesse_humain: ["boite, ensanglanté, tient son bras et dit « ne tirez pas »", "ensanglanté, avance lentement en levant une main ouverte"],
  },
  en: {
    zombie: ["slow jerky walk, grunts, arms stretched out", "grey skin, slack jaw, keeps walking without stopping",
             "stumbles, never blinks, constant groaning"],
    humain: ["runs toward the shelter shouting \"help me!\"", "waves both arms, carries a backpack",
             "runs in a zigzag, calls out to friends by name"],
    blesse_zombie: ["limping, bloodied, doesn't respond when called", "bloodied, head tilted, walks in a straight line without speaking"],
    blesse_humain: ["limping, bloodied, holds their arm and says \"don't shoot\"", "bloodied, walks slowly raising an open hand"],
  },
};

export const REACTION_I18N = {
  fr: { humain: "s'arrête immédiatement et lève les deux mains", blesse_humain: "s'arrête et lève sa main valide en criant « je suis vivant ! »",
        zombie: "ne réagit pas et continue d'avancer vers l'abri", blesse_zombie: "tourne la tête vers le bruit puis continue d'avancer sans s'arrêter" },
  en: { humain: "stops immediately and raises both hands", blesse_humain: "stops and raises their good hand shouting \"I'm alive!\"",
        zombie: "does not react and keeps walking toward the shelter", blesse_zombie: "turns its head toward the noise then keeps walking without stopping" },
};

// nombre de descriptions par nature (identique en FR et EN)
export const NB_DESC = Object.fromEntries(Object.entries(DESC_I18N.fr).map(([n, l]) => [n, l.length]));
