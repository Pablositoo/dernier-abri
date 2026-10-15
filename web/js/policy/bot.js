// Bot naïf (mode 3) : tire sur le plus proche à moins de 30 m, sauf s'il appelle à l'aide.
const APPEL_AIDE = /aidez-moi|help me/i;

export const botNaif = vis => vis.find(c => c.distance < 30 && !APPEL_AIDE.test(c.desc)) ?? null;
